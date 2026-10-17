"""Escalation detection and dispatch.

One scan, two outputs per item:

1. an in-app :class:`~core.notifications.Notification` (so it shows in the
   bell and the notifications page), and
2. an **email** to the person responsible — honouring their
   ``UserPreference`` toggles.

The scan is **idempotent**. ``create_notification`` refuses to raise a second
notification for the same unresolved object, and email is only sent for items
whose notification was newly created. Running the job hourly therefore alerts
once, not sixty times a day. Overdue items are not chased again until the
underlying condition is either resolved (notification auto-clears) or changes
state.

Who gets the mail: the named owner (assignee / owner / approver) if there is
one, otherwise the department HOD. If neither exists the item is still raised
in-app for the department, and mail falls back to
``settings.ESCALATION_FALLBACK_EMAILS``.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .emails import email_pref_allows, send_escalation_email
from .notifications import create_notification

logger = logging.getLogger(__name__)


@dataclass
class Escalation:
    """One item that has breached a due date or tolerance threshold."""

    kind: str
    title: str
    action_url: str
    dept: object
    ref: object
    flag: str = 'email_on_escalation'
    severity: str = 'warning'
    meta: str = ''

    # -- recipient resolution ------------------------------------------------

    def owner(self):
        for attr in ('assigned_to', 'owner_user', 'approver'):
            user = getattr(self.ref, attr, None)
            if user is not None:
                return user
        return None

    def hod(self):
        if self.dept is None:
            return None
        return self.dept.users.filter(is_hod=True).first()

    def responsible_users(self):
        user = self.owner() or self.hod()
        return [user] if user else []

    def as_item(self):
        return {
            'title': self.title,
            'meta': self.meta,
            'url': self.action_url,
            'severity': self.severity,
        }


# ---------------------------------------------------------------------------
# Collectors — one per source. Each is a single queryset (no N+1).
# ---------------------------------------------------------------------------

def _risk_escalations(grace_cutoff, warn_cutoff):
    from risks.models import Risk

    out = []
    qs = (
        Risk.objects.filter(escalated=True)
        .exclude(status='closed')
        .select_related('owner_user', 'owner_dept')
    )
    for risk in qs:
        out.append(Escalation(
            kind='risk_escalated',
            title=f'Risk {risk.pk}: {risk.title[:110]} is beyond risk capacity',
            action_url=reverse('risks:detail', args=[risk.pk]),
            dept=risk.owner_dept,
            ref=risk,
            flag='email_on_risk_breach',
            severity='danger',
            meta=f'Inherent {risk.inherent_score} · residual {risk.residual_score}'
                 f' · {risk.get_status_display()}',
        ))

    overdue = (
        Risk.objects.filter(target_close_date__lt=grace_cutoff)
        .exclude(status='closed')
        .select_related('owner_user', 'owner_dept')
    )
    for risk in overdue:
        out.append(Escalation(
            kind='risk_overdue',
            title=f'Risk {risk.pk}: {risk.title[:110]} is past its target date',
            action_url=reverse('risks:detail', args=[risk.pk]),
            dept=risk.owner_dept,
            ref=risk,
            flag='email_on_escalation',
            meta=f'Target {risk.target_close_date} · {risk.days_overdue} day(s) overdue',
        ))
    return out


def _audit_escalations(grace_cutoff, warn_cutoff):
    from audits.models import ActionItem, AuditFinding

    out = []
    findings = (
        AuditFinding.objects.filter(due_date__lt=grace_cutoff)
        .exclude(status__in=['resolved', 'accepted', 'closed'])
        .select_related('owner_user', 'owner_dept')
    )
    for finding in findings:
        out.append(Escalation(
            kind='finding_overdue',
            title=f'Finding: {finding.title[:110]} is overdue',
            action_url=reverse('audits:finding_detail', args=[finding.pk]),
            dept=finding.owner_dept,
            ref=finding,
            flag='email_on_audit_finding',
            meta=f'{finding.get_severity_display()} · due {finding.due_date}'
                 f' · {finding.days_overdue} day(s) overdue',
        ))

    actions = (
        ActionItem.objects.filter(due_date__lt=grace_cutoff)
        .exclude(status__in=['completed', 'cancelled'])
        .select_related('owner_user', 'owner_dept')
    )
    for action in actions:
        out.append(Escalation(
            kind='action_overdue',
            title=f'Action {action.action_id}: {action.title[:100]} is overdue',
            action_url=reverse('audits:action_detail', args=[action.pk]),
            dept=action.owner_dept,
            ref=action,
            flag='email_on_audit_finding',
            meta=f'Due {action.due_date} · {abs(action.days_until_due)} day(s) overdue',
        ))
    return out


def _ticket_escalations(grace_cutoff, warn_cutoff):
    from tickets.models import Ticket

    out = []
    tickets = (
        Ticket.objects.filter(due_date__lt=grace_cutoff)
        .exclude(status__in=['resolved', 'closed', 'cancelled'])
        .select_related('owner_dept', 'assigned_to')
    )
    for ticket in tickets:
        overdue_days = (timezone.localdate() - ticket.due_date).days
        out.append(Escalation(
            kind='ticket_overdue',
            title=f'{ticket.ticket_id}: {ticket.title[:110]} is overdue',
            action_url=reverse('tickets:detail', args=[ticket.pk]),
            dept=ticket.owner_dept,
            ref=ticket,
            flag='email_on_ticket_assigned',
            meta=f'{ticket.get_priority_display()} priority · due {ticket.due_date}'
                 f' · {overdue_days} day(s) overdue',
        ))
    return out


def _exception_escalations(grace_cutoff, warn_cutoff):
    from risks.models import RiskException

    out = []
    qs = (
        RiskException.objects.filter(
            status__in=['pending', 'active'], expiry_date__lte=warn_cutoff,
        )
        .select_related('risk__owner_dept', 'approver', 'risk')
    )
    for exc in qs:
        days = exc.days_until_expiry
        if days is None:
            continue
        detail = (
            f'expired {abs(days)} day(s) ago' if days < 0
            else f'expires in {days} day(s)'
        )
        out.append(Escalation(
            kind='exception_expiring',
            title=f'{exc.exception_id}: {exc.title[:100]} — {detail}',
            action_url=reverse('risks:exception_detail', args=[exc.pk]),
            dept=exc.risk.owner_dept,
            ref=exc,
            flag='email_on_escalation',
            severity='danger' if days < 0 else 'warning',
            meta=f'Expiry {exc.expiry_date} · {exc.get_status_display()}',
        ))
    return out


def _vendor_escalations(grace_cutoff, warn_cutoff):
    from vendors.models import Vendor

    out = []
    qs = (
        Vendor.objects.filter(contract_renewal_date__lte=warn_cutoff)
        .exclude(status='terminated')
        .select_related('owner_dept', 'owner_user')
    )
    for vendor in qs:
        days = vendor.days_to_renewal
        detail = (
            f'contract expired {abs(days)} day(s) ago' if days < 0
            else f'contract renews in {days} day(s)'
        )
        out.append(Escalation(
            kind='vendor_contract_expired',
            title=f'{vendor.name}: {detail}',
            action_url=reverse('vendors:detail', args=[vendor.pk]),
            dept=vendor.owner_dept,
            ref=vendor,
            flag='email_on_escalation',
            severity='danger' if days < 0 else 'warning',
            meta=f'Tier {vendor.tier} · renewal {vendor.contract_renewal_date}',
        ))
    return out


def _kri_escalations(grace_cutoff, warn_cutoff):
    from kris.models import KRI

    out = []
    for kri in KRI.objects.select_related('owner_user', 'owner_dept').prefetch_related('readings'):
        if kri.rag_status != 'red':
            continue
        out.append(Escalation(
            kind='kri_red',
            title=f'KRI #{kri.pk}: {kri.name[:100]} has breached tolerance',
            action_url=reverse('kris:detail', args=[kri.pk]),
            dept=kri.owner_dept,
            ref=kri,
            flag='email_on_kri_red',
            severity='danger',
            meta='Latest reading is outside the accepted tolerance',
        ))
    return out


def _vulnerability_escalations(grace_cutoff, warn_cutoff):
    from vulnerabilities.models import Finding

    out = []
    qs = (
        Finding.objects.filter(sla_due_date__lt=grace_cutoff)
        .exclude(status__in=Finding.CLOSED_STATUSES)
        .select_related('owner_dept', 'assigned_to', 'asset', 'vulnerability')
    )
    for finding in qs:
        overdue_days = (timezone.localdate() - finding.sla_due_date).days
        out.append(Escalation(
            kind='vuln_sla_breach',
            title=f'{finding.vulnerability.cve_id}: {finding.asset.name} past SLA',
            action_url=reverse('vulnerabilities:finding_detail', args=[finding.pk]),
            dept=finding.owner_dept,
            ref=finding,
            flag='email_on_vuln_sla',
            severity='danger',
            meta=f'SLA due {finding.sla_due_date} · {overdue_days} day(s) over',
        ))
    return out


_COLLECTORS = (
    _risk_escalations,
    _audit_escalations,
    _ticket_escalations,
    _exception_escalations,
    _vendor_escalations,
    _kri_escalations,
    _vulnerability_escalations,
)


def collect_escalations(today=None):
    """Return every currently-escalating item across all sources."""
    today = today or timezone.localdate()
    grace_cutoff = today - timedelta(days=getattr(settings, 'ESCALATION_GRACE_DAYS', 1))
    warn_cutoff = today + timedelta(days=getattr(settings, 'ESCALATION_WARN_DAYS', 14))

    found = []
    for collector in _COLLECTORS:
        try:
            found.extend(collector(grace_cutoff, warn_cutoff))
        except Exception:  # pragma: no cover - one bad source must not stop the rest
            logger.exception('Escalation collector %s failed', collector.__name__)
    return found


def _fallback_addresses():
    return [a for a in (getattr(settings, 'ESCALATION_FALLBACK_EMAILS', []) or []) if a]


def run_escalations(*, dry_run=False, send_emails=True):
    """Scan, raise in-app notifications, and email the responsible people.

    Returns a summary dict. With ``dry_run`` nothing is written.
    """
    escalations = collect_escalations()

    summary = {
        'found': len(escalations),
        'created': 0,
        'emailed': 0,
        'recipients': 0,
        'items': [e.as_item() for e in escalations],
    }
    if dry_run:
        return summary

    # 1. Raise in-app notifications. create_notification() returns None when an
    #    identical unresolved notification already exists — that is our
    #    "already alerted" signal, and those items are skipped for email too.
    fresh = []
    for esc in escalations:
        notification = create_notification(
            kind=esc.kind,
            title=esc.title,
            action_url=esc.action_url,
            owner_dept=esc.dept,
            ref_obj=esc.ref,
            recipient=esc.owner(),
        )
        if notification is not None:
            fresh.append(esc)
    summary['created'] = len(fresh)

    if not send_emails:
        return summary

    # 2. Group the *new* items by (recipient, preference flag) so each email
    #    respects exactly one toggle and nobody gets a mixed-purpose blast.
    buckets = defaultdict(list)
    fallback_buckets = defaultdict(list)
    for esc in fresh:
        targets = [
            user for user in esc.responsible_users()
            if email_pref_allows(user, esc.flag)
        ]
        if targets:
            for user in targets:
                buckets[(user.pk, esc.flag)].append((user, esc))
        else:
            # No opted-in owner/HOD — send to the configured fallback address.
            fallback_buckets[esc.flag].append(esc)

    recipients = set()
    for (user_pk, _flag), entries in buckets.items():
        user = entries[0][0]
        items = [esc.as_item() for _u, esc in entries]
        dept_name = next((esc.dept.name for _u, esc in entries if esc.dept), None)
        if send_escalation_email([user], items, dept_name=dept_name):
            recipients.add(user_pk)
        summary['emailed'] += len(items)

    fallback = _fallback_addresses()
    if fallback:
        for _flag, entries in fallback_buckets.items():
            items = [esc.as_item() for esc in entries]
            if send_escalation_email(fallback, items):
                summary['emailed'] += len(items)

    summary['recipients'] = len(recipients)
    return summary
