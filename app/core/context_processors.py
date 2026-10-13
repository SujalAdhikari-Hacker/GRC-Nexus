"""
Context processors that run on every page render.
Injects pending-action counts into every template's context.
"""


def pending_actions(request):
    if not request.user.is_authenticated:
        return {}

    from core.pending_actions import all_pending

    user = request.user
    dept = None if user.is_superuser else user.department
    is_super = user.is_superuser

    p = all_pending(dept=dept, is_super=is_super)

    result = {
        'pending_assets':   p['assets'],
        'pending_vendors':  p['vendors'],
        'pending_policies': p['policies'],
        'pending_controls': p['controls'],
        'pending_risks':    p['risks'],
        'pending_kris':     p['kris'],
        'pending_audits':   p['audits'],
    }

    # Section totals for the header dots
    result['pending_inventory_total'] = (
        p['assets']['count'] +
        p['vendors']['count'] +
        p['policies']['count']
    )
    result['pending_risk_controls_total'] = (
        p['risks']['count'] +
        p['controls']['count'] +
        p['kris']['count']
    )
    result['pending_audit_total'] = p['audits']['count']

    return result


def notification_count(request):
    """Add unread notification count to every template's context."""
    if not request.user.is_authenticated:
        return {'unread_notification_count': 0}

    try:
        from core.notification_registry import (
            unread_count_for, refresh_notifications,
        )
        # Lazy clear first
        refresh_notifications(
            dept=request.user.department,
            is_super=request.user.is_superuser,
        )
        count = unread_count_for(request.user)
    except Exception:
        count = 0
    return {'unread_notification_count': count}


def recent_notifications_context(request):
    """Add recent (5) notifications + unread count to every template."""
    if not request.user.is_authenticated:
        return {'recent_notifications': [], 'unread_notification_count': 0}

    try:
        from core.notifications import Notification
        from core.notification_registry import refresh_notifications, unread_count_for

        refresh_notifications(
            dept=request.user.department,
            is_super=request.user.is_superuser,
        )

        qs = Notification.objects.filter(is_cleared=False)
        if not request.user.is_superuser:
            if not request.user.department_id:
                return {'recent_notifications': [], 'unread_notification_count': 0}
            qs = qs.filter(owner_dept_id=request.user.department_id)

        recent = list(qs.order_by('-created_at')[:5])
        return {
            'recent_notifications': recent,
            'unread_notification_count': unread_count_for(request.user),
        }
    except Exception:
        return {'recent_notifications': [], 'unread_notification_count': 0}


def notification_sections(request):
    """Per-section and per-link unread notification counts for the sidebar."""
    empty = {
        'notif_assets': 0, 'notif_vendors': 0, 'notif_policies': 0,
        'notif_risks': 0, 'notif_controls': 0, 'notif_kris': 0,
        'notif_findings': 0, 'notif_tickets': 0,
        'notif_section_inventory': 0,
        'notif_section_risk': 0,
        'notif_section_audit': 0,
    }
    if not request.user.is_authenticated:
        return empty

    try:
        from core.notifications import Notification
        from core.notification_registry import refresh_notifications

        refresh_notifications(
            dept=request.user.department,
            is_super=request.user.is_superuser,
        )

        qs = Notification.objects.filter(is_cleared=False, is_read=False)
        if not request.user.is_superuser:
            if not request.user.department_id:
                return empty
            qs = qs.filter(owner_dept_id=request.user.department_id)

        def count(*kinds):
            return qs.filter(kind__in=kinds).count()

        notif_assets = count('asset_needs_vendor', 'asset_needs_owner', 'asset_needs_policies')
        notif_vendors = count('vendor_needs_assessment')
        notif_policies = count('policy_needs_approval', 'policy_review_due')
        notif_risks = count('risk_needs_assessment', 'risk_needs_controls')
        notif_controls = count('control_needs_testing', 'control_needs_mapping')
        notif_kris = count('kri_needs_reading')
        notif_findings = count(
            'audit_needs_lead', 'finding_needs_owner',
            'finding_needs_actions', 'action_needs_owner',
        )
        notif_tickets = count('ticket_unassigned')

        return {
            'notif_assets': notif_assets,
            'notif_vendors': notif_vendors,
            'notif_policies': notif_policies,
            'notif_risks': notif_risks,
            'notif_controls': notif_controls,
            'notif_kris': notif_kris,
            'notif_findings': notif_findings,
            'notif_tickets': notif_tickets,
            'notif_section_inventory': notif_assets + notif_vendors + notif_policies,
            'notif_section_risk': notif_risks + notif_controls + notif_kris,
            'notif_section_audit': notif_findings,
        }
    except Exception:
        return empty


def user_preference_context(request):
    """Expose the current user's preferences to every template."""
    empty = {
        'user_theme_pref': 'system',
        'user_date_format': 'Y-m-d',
        'user_time_format': 'H:i',
        'user_timezone_pref': 'UTC',
    }
    if not request.user.is_authenticated:
        return empty
    try:
        from core.settings_model import UserPreference
        pref = UserPreference.get_for(request.user)
        if not pref:
            return empty
        return {
            'user_theme_pref': pref.theme or 'system',
            'user_date_format': pref.date_format or 'Y-m-d',
            'user_time_format': pref.time_format or 'H:i',
            'user_timezone_pref': pref.timezone or 'UTC',
        }
    except Exception:
        return empty
