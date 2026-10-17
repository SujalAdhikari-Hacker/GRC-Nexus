"""
Auto-clear registry.

Each notification kind maps to a predicate function. When the function
returns True, the notification is marked as cleared.

Evaluated lazily: on every count/list render, so we don't need to
touch every save signal in the whole app.
"""
from datetime import timedelta

from django.apps import apps
from django.utils import timezone

from .notifications import Notification


def _risk_assessed(obj):
    return obj.status != 'identified'


def _policy_not_draft(obj):
    return obj.status != 'draft'


def _policy_review_ok(obj):
    if not obj.next_review_date:
        return True
    return obj.next_review_date > (timezone.now().date() + timedelta(days=30))


def _control_tested(obj):
    return obj.effectiveness_rating != 'not_tested'


def _control_mapped(obj):
    return obj.framework_controls.exists() or obj.framework_mappings.exists()


def _kri_has_recent_reading(obj):
    cutoff = timezone.now().date() - timedelta(days=30)
    return obj.readings.filter(reading_date__gte=cutoff).exists()


def _ticket_assigned(obj):
    return obj.assigned_to_id is not None


def _exception_no_longer_expiring(obj):
    """Clear once the exception is actioned, or pushed far enough out."""
    from django.conf import settings
    if obj.status in ('revoked', 'expired'):
        return True
    days = obj.days_until_expiry
    if days is None:
        return True
    return days > getattr(settings, 'ESCALATION_WARN_DAYS', 14)


def _vendor_contract_ok(obj):
    return not (obj.is_contract_expired or obj.is_renewal_due_soon)


CLEAR_RULES = {
    'asset_needs_vendor':      lambda o: o.vendors.exists(),
    'asset_needs_owner':       lambda o: o.owner_user_id is not None,
    'asset_needs_policies':    lambda o: o.policies.exists(),
    'risk_needs_assessment':   _risk_assessed,
    'risk_needs_controls':     lambda o: o.controls.exists(),
    'vendor_needs_assessment': lambda o: o.assessments.exists(),
    'policy_needs_approval':   _policy_not_draft,
    'policy_review_due':       _policy_review_ok,
    'control_needs_testing':   _control_tested,
    'control_needs_mapping':   _control_mapped,
    'kri_needs_reading':       _kri_has_recent_reading,
    'audit_needs_lead':        lambda o: o.auditor_lead_id is not None,
    'finding_needs_owner':     lambda o: o.owner_user_id is not None,
    'finding_needs_actions':   lambda o: o.action_items.exists(),
    'action_needs_owner':      lambda o: o.owner_user_id is not None,
    'ticket_unassigned':       _ticket_assigned,
    # Escalations clear as soon as the underlying condition is resolved.
    'risk_escalated':          lambda o: not o.escalated,
    'risk_overdue':            lambda o: not o.is_overdue,
    'finding_overdue':         lambda o: not o.is_overdue,
    'action_overdue':          lambda o: not o.is_overdue,
    'ticket_overdue':          lambda o: not o.is_overdue,
    'exception_expiring':      _exception_no_longer_expiring,
    'vendor_contract_expired': _vendor_contract_ok,
    'kri_red':                 lambda o: o.rag_status != 'red',
    'vuln_sla_breach':         lambda o: not o.is_overdue,
}


def refresh_notifications(dept=None, is_super=False):
    """
    Check every active notification and mark it cleared if its condition
    is now met (or the linked object has been deleted).

    Returns the number of notifications cleared.

    Referenced objects are batch-loaded with ``in_bulk`` — one query per
    model rather than one query per notification. A department with 500 open
    alerts used to cost 500+ queries on every sweep.
    """
    qs = Notification.objects.filter(is_cleared=False)
    if not is_super:
        if dept is None:
            return 0
        qs = qs.filter(owner_dept=dept)

    notifications = list(qs)

    # Group referenced ids by model so we can load them in one query each.
    ids_by_model = {}
    for n in notifications:
        if n.ref_model and n.ref_id:
            ids_by_model.setdefault(n.ref_model, set()).add(n.ref_id)

    loaded = {}
    for ref_model, ids in ids_by_model.items():
        try:
            app_label, model_name = ref_model.split('.')
            Model = apps.get_model(app_label, model_name)
        except Exception:
            loaded[ref_model] = {}
            continue
        try:
            loaded[ref_model] = Model.objects.in_bulk(ids)
        except Exception:
            loaded[ref_model] = {}

    cleared_count = 0
    for n in notifications:
        if not n.ref_model or not n.ref_id:
            continue
        obj = loaded.get(n.ref_model, {}).get(n.ref_id)
        if obj is None:
            n.mark_cleared()
            cleared_count += 1
            continue
        rule = CLEAR_RULES.get(n.kind)
        if rule is None:
            continue
        try:
            if rule(obj):
                n.mark_cleared()
                cleared_count += 1
        except Exception:
            continue

    return cleared_count


def unread_count_for(user):
    """Return the number of unread, uncleared notifications visible to this user."""
    if not user.is_authenticated:
        return 0
    from django.db.models import Q

    qs = Notification.objects.filter(is_read=False, is_cleared=False)
    if not user.is_superuser:
        cond = Q(recipient=user)
        if user.department_id:
            cond |= Q(owner_dept_id=user.department_id)
        qs = qs.filter(cond)
    return qs.count()


# The clear sweep is O(notifications) and runs while rendering *every* page
# (the notification bell is in the base template). Throttle it so a burst of
# page views does not re-walk the whole queue each time; the cache is a plain
# per-process locmem cache, so worst case each worker sweeps once per window.
REFRESH_THROTTLE_SECONDS = 60


def refresh_notifications_throttled(dept=None, is_super=False, force=False):
    """Run :func:`refresh_notifications` at most once per scope per window.

    Returns the number cleared by *this* call (0 when the sweep was skipped).
    """
    from django.core.cache import cache

    scope = 'super' if is_super else f'dept-{dept.pk if dept else "none"}'
    key = f'grc:notif-refresh:{scope}'
    if not force and cache.get(key) is not None:
        return 0
    cleared = refresh_notifications(dept=dept, is_super=is_super)
    cache.set(key, 1, REFRESH_THROTTLE_SECONDS)
    return cleared
