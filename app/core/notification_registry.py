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
}


def _resolve_object(ref_model, ref_id):
    try:
        app_label, model_name = ref_model.split('.')
        Model = apps.get_model(app_label, model_name)
        return Model.objects.filter(pk=ref_id).first()
    except Exception:
        return None


def refresh_notifications(dept=None, is_super=False):
    """
    Check every active notification and mark it cleared if its condition
    is now met (or the linked object has been deleted).

    Returns the number of notifications cleared.
    """
    qs = Notification.objects.filter(is_cleared=False)
    if not is_super:
        if dept is None:
            return 0
        qs = qs.filter(owner_dept=dept)

    cleared_count = 0
    for n in qs:
        if not n.ref_model or not n.ref_id:
            continue
        obj = _resolve_object(n.ref_model, n.ref_id)
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
    qs = Notification.objects.filter(is_read=False, is_cleared=False)
    if not user.is_superuser:
        if not user.department_id:
            return 0
        qs = qs.filter(owner_dept_id=user.department_id)
    return qs.count()
