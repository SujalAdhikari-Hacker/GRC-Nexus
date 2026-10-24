"""
Alert engine — scans the system for conditions that should generate a ticket.

Design:
- Each rule is a pure function returning a list of "alert events"
- An alert event is a dict: {obj, title, description, priority, dept}
- The engine deduplicates — skips events where an open ticket already exists
  for that object (matching content_type + object_id + status=open-ish)
"""
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


# ==================================================================
# HELPERS
# ==================================================================

def _open_ticket_exists(obj):
    """True if an OPEN alert ticket already exists for this object."""
    from .models import Ticket
    ct = ContentType.objects.get_for_model(obj)
    return Ticket.objects.filter(
        content_type=ct,
        object_id=obj.pk,
        source='alert',
        status__in=['open', 'assigned', 'in_progress', 'blocked'],
    ).exists()


def _create_ticket(event):
    """Create a Ticket from an alert event dict."""
    from .models import Ticket
    obj = event['obj']
    ct = ContentType.objects.get_for_model(obj)
    return Ticket.objects.create(
        title=event['title'],
        description=event['description'],
        source='alert',
        content_type=ct,
        object_id=obj.pk,
        priority=event['priority'],
        status='open',
        owner_dept=event['dept'],
    )


# ==================================================================
# RULES
# ==================================================================

def rule_risk_appetite_breach():
    """Risks whose residual exceeds appetite."""
    from risks.models import Risk
    events = []
    qs = Risk.objects.filter(appetite_breached=True).exclude(status='closed').select_related('owner_dept')
    for r in qs:
        if _open_ticket_exists(r):
            continue
        events.append({
            'obj': r,
            'title': f'Risk appetite breach: {r.title[:80]}',
            'description': (
                f'Risk "{r.title}" has a residual score of {r.residual_score} '
                f'which exceeds the appetite threshold.\n\n'
                f'Owner department: {r.owner_dept.name}\n'
                f'Inherent: {r.inherent_score} · Residual: {r.residual_score}\n\n'
                f'Action: reduce exposure via controls/treatments, or request an exception.'
            ),
            'priority': 4 if r.inherent_score >= 20 else 3,
            'dept': r.owner_dept,
        })
    return events


def rule_kev_finding_on_critical_asset():
    """CISA KEV findings on assets with criticality >= 3."""
    from vulnerabilities.models import Finding
    events = []
    qs = Finding.objects.filter(
        vulnerability__kev_status=True,
        asset__criticality__gte=3,
    ).exclude(status__in=['remediated', 'accepted', 'false_positive']).select_related(
        'vulnerability', 'asset', 'owner_dept'
    )
    for f in qs:
        if _open_ticket_exists(f):
            continue
        events.append({
            'obj': f,
            'title': f'KEV: {f.vulnerability.cve_id or "Vuln"} on {f.asset.name[:40]}',
            'description': (
                f'A CISA Known Exploited Vulnerability is present on a critical asset.\n\n'
                f'CVE: {f.vulnerability.cve_id or "—"}\n'
                f'CVSS: {f.vulnerability.cvss_score}\n'
                f'Asset: {f.asset.name} (criticality {f.asset.criticality})\n'
                f'SLA due: {f.sla_due_date or "—"}\n\n'
                f'This is actively exploited in the wild. Remediate urgently.'
            ),
            'priority': 4,
            'dept': f.owner_dept,
        })
    return events


def rule_control_ineffective():
    """Implemented controls assessed as ineffective."""
    from controls.models import Control
    events = []
    qs = Control.objects.filter(
        status='implemented',
        effectiveness_rating='ineffective',
    ).select_related('owner_dept')
    for c in qs:
        if _open_ticket_exists(c):
            continue
        events.append({
            'obj': c,
            'title': f'Control ineffective: {c.code} — {c.name[:50]}',
            'description': (
                f'Control "{c.name}" ({c.code}) is marked ineffective '
                f'but still in "implemented" status.\n\n'
                f'Department: {c.owner_dept.name}\n\n'
                f'Action: redesign, retire, or add compensating controls.'
            ),
            'priority': 3,
            'dept': c.owner_dept,
        })
    return events


def rule_kri_red():
    """KRIs whose RAG status is red."""
    from kris.models import KRI
    events = []
    for k in KRI.objects.select_related('owner_dept'):
        if k.rag_status != 'red':
            continue
        if _open_ticket_exists(k):
            continue
        events.append({
            'obj': k,
            'title': f'KRI red: {k.name[:80]}',
            'description': (
                f'KRI "{k.name}" has crossed the red threshold.\n\n'
                f'Current value: {k.current_value} {k.unit}\n'
                f'Red threshold: {k.red_threshold}\n'
                f'Amber threshold: {k.amber_threshold}\n'
                f'Direction: {k.get_direction_display()}\n\n'
                f'Review and take corrective action.'
            ),
            'priority': 3,
            'dept': k.owner_dept,
        })
    return events


def rule_action_item_overdue():
    """Action items past their due date."""
    from audits.models import ActionItem
    today = timezone.localdate()
    events = []
    qs = ActionItem.objects.filter(due_date__lt=today).exclude(
        status__in=['completed', 'cancelled']
    ).select_related('owner_dept')
    for a in qs:
        if _open_ticket_exists(a):
            continue
        events.append({
            'obj': a,
            'title': f'Action overdue: {a.action_id} — {a.title[:50]}',
            'description': (
                f'Action item "{a.title}" is past its due date.\n\n'
                f'Action ID: {a.action_id}\n'
                f'Due date: {a.due_date}\n'
                f'Priority: {a.get_priority_display()}\n'
                f'Owner: {a.owner_user.username if a.owner_user else a.owner_dept.name}\n'
                f'Progress: {a.progress_percent}%\n\n'
                f'Update status or escalate.'
            ),
            'priority': a.priority,
            'dept': a.owner_dept,
        })
    return events


def rule_audit_finding_overdue():
    """Audit findings past their remediation due date."""
    from audits.models import AuditFinding
    today = timezone.localdate()
    events = []
    qs = AuditFinding.objects.filter(due_date__lt=today).exclude(
        status__in=['resolved', 'closed', 'accepted']
    ).select_related('owner_dept')
    for f in qs:
        if _open_ticket_exists(f):
            continue
        events.append({
            'obj': f,
            'title': f'Audit finding overdue: {f.title[:60]}',
            'description': (
                f'Audit finding "{f.title}" is past its remediation deadline.\n\n'
                f'Severity: {f.get_severity_display()}\n'
                f'Due date: {f.due_date}\n'
                f'Owner: {f.owner_user.username if f.owner_user else f.owner_dept.name}\n'
                f'Status: {f.get_status_display()}\n\n'
                f'Review and either remediate or request an extension.'
            ),
            'priority': {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}.get(f.severity, 2),
            'dept': f.owner_dept,
        })
    return events


def rule_vendor_high_risk():
    """Latest vendor assessments flagged high or critical risk."""
    from vendors.models import VendorAssessment
    events = []
    seen_vendors = set()
    qs = VendorAssessment.objects.select_related(
        'vendor', 'vendor__owner_dept', 'assessor'
    ).order_by('vendor_id', '-assessment_date')

    for a in qs:
        if a.vendor_id in seen_vendors:
            continue
        seen_vendors.add(a.vendor_id)
        if a.overall_risk_rating not in ('high', 'critical'):
            continue
        if _open_ticket_exists(a):
            continue
        events.append({
            'obj': a,
            'title': f'Vendor {a.overall_risk_rating.title()} risk: {a.vendor.name[:50]}',
            'description': (
                f'Vendor "{a.vendor.name}" scored {a.overall_score}/100 — '
                f'{a.get_overall_risk_rating_display()} risk.\n\n'
                f'Assessed by: {a.assessor.username if a.assessor else "—"}\n'
                f'Assessment date: {a.assessment_date}\n\n'
                f'Review the vendor\'s risk profile and consider mitigation.'
            ),
            'priority': 4 if a.overall_risk_rating == 'critical' else 3,
            'dept': a.vendor.owner_dept,
        })
    return events


def rule_policy_review_due():
    """Approved policies with review dates within 30 days (or overdue)."""
    from policies.models import Policy
    today = timezone.localdate()
    threshold = today + timedelta(days=30)
    events = []
    qs = Policy.objects.filter(
        status='approved',
        next_review_date__isnull=False,
        next_review_date__lte=threshold,
    ).select_related('owner_dept')
    for p in qs:
        if _open_ticket_exists(p):
            continue
        overdue = p.next_review_date < today
        events.append({
            'obj': p,
            'title': f'Policy review {"overdue" if overdue else "due"}: {p.code}',
            'description': (
                f'Policy "{p.title}" ({p.code}) is scheduled for review.\n\n'
                f'Next review date: {p.next_review_date}\n'
                f'Owner department: {p.owner_dept.name}\n\n'
                f'Review the policy, update if needed, and set a new review date.'
            ),
            'priority': 3 if overdue else 2,
            'dept': p.owner_dept,
        })
    return events


def rule_evidence_weak_score():
    """Evidence scored below 50."""
    from audits.models import EvidenceScore
    events = []
    qs = EvidenceScore.objects.filter(total_score__lt=50).select_related(
        'evidence', 'evidence__owner_dept'
    )
    for s in qs:
        if _open_ticket_exists(s):
            continue
        events.append({
            'obj': s,
            'title': f'Weak evidence: {s.evidence.title[:60]}',
            'description': (
                f'Evidence "{s.evidence.title}" scored {s.total_score}/100 — below the 50 threshold.\n\n'
                f'Relevance: {s.relevance}/20 · Completeness: {s.completeness}/20\n'
                f'Timeliness: {s.timeliness}/20 · Reliability: {s.reliability}/20\n'
                f'Sufficiency: {s.sufficiency}/20\n\n'
                f'Consider supplementing with stronger evidence.'
            ),
            'priority': 2,
            'dept': s.evidence.owner_dept,
        })
    return events


# ==================================================================
# ENGINE
# ==================================================================

RULES = [
    ('risk_appetite_breach',          rule_risk_appetite_breach),
    ('kev_finding_on_critical_asset', rule_kev_finding_on_critical_asset),
    ('control_ineffective',           rule_control_ineffective),
    ('kri_red',                       rule_kri_red),
    ('action_item_overdue',           rule_action_item_overdue),
    ('audit_finding_overdue',         rule_audit_finding_overdue),
    ('vendor_high_risk',              rule_vendor_high_risk),
    ('policy_review_due',             rule_policy_review_due),
    ('evidence_weak_score',           rule_evidence_weak_score),
]


def scan_and_create_tickets(verbose=False):
    """
    Run every rule; create tickets for new alerts.
    Returns dict {rule_name: {'events_found': N, 'tickets_created': M}}
    """
    results = {}
    for rule_name, rule_fn in RULES:
        try:
            events = rule_fn()
        except Exception as e:
            if verbose:
                print(f'  [{rule_name}] ERROR: {e}')
            results[rule_name] = {'error': str(e)}
            continue

        created = 0
        for ev in events:
            try:
                _create_ticket(ev)
                created += 1
                if verbose:
                    print(f'  [{rule_name}] created: {ev["title"][:70]}')
            except Exception as e:
                if verbose:
                    print(f'  [{rule_name}] create failed: {e}')

        results[rule_name] = {'events_found': len(events), 'tickets_created': created}

    return results


# The scan walks the whole risk/control/finding/action set and creates tickets.
# The dashboard loads it on *every* page view and the login hook fires it on
# every login, so runs share one cache window — otherwise a busy deployment
# re-walks everything each time two tabs are refreshed in succession.
SCAN_THROTTLE_SECONDS = 60
SCAN_THROTTLE_KEY = 'grc:alert-scan'


def scan_and_create_tickets_throttled(force=False):
    """Run the alert scan at most once per :data:`SCAN_THROTTLE_SECONDS`.

    Returns the scan result dict, or ``None`` when this call was skipped
    because another one ran inside the window.
    """
    from django.core.cache import cache

    if not force and cache.get(SCAN_THROTTLE_KEY) is not None:
        return None
    cache.set(SCAN_THROTTLE_KEY, 1, SCAN_THROTTLE_SECONDS)
    return scan_and_create_tickets(verbose=False)