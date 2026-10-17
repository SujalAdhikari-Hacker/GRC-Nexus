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


_SNAPSHOT_ATTR = '_grc_notification_snapshot'


def _notification_snapshot(request):
    """Compute the notification snapshot once per request.

    Previously three separate context processors each called
    ``refresh_notifications`` (which walks every uncleared notification and
    runs a query per row) and re-counted unread notifications — three times
    per page render. The snapshot is now computed once and memoised on the
    request, and the expensive clear-rule sweep is throttled through the cache
    so it does not run on every single page view.
    """
    cached = getattr(request, _SNAPSHOT_ATTR, None)
    if cached is not None:
        return cached

    empty = {
        'recent_notifications': [],
        'unread_notification_count': 0,
        'notif_assets': 0, 'notif_vendors': 0, 'notif_policies': 0,
        'notif_risks': 0, 'notif_controls': 0, 'notif_kris': 0,
        'notif_findings': 0, 'notif_tickets': 0,
        'notif_section_inventory': 0,
        'notif_section_risk': 0,
        'notif_section_audit': 0,
    }

    user = request.user
    if not user.is_authenticated:
        setattr(request, _SNAPSHOT_ATTR, empty)
        return empty
    if not user.is_superuser and not user.department_id:
        # A department-less account sees nothing — never the whole organisation.
        setattr(request, _SNAPSHOT_ATTR, empty)
        return empty

    try:
        from django.db.models import Count

        from core.notification_registry import refresh_notifications_throttled
        from core.notifications import Notification

        refresh_notifications_throttled(
            dept=user.department, is_super=user.is_superuser,
        )

        base = Notification.objects.filter(is_cleared=False)
        if not user.is_superuser:
            base = base.filter(owner_dept_id=user.department_id)

        recent = list(base.order_by('-created_at')[:5])

        unread = base.filter(is_read=False)
        unread_total = unread.count()

        # One GROUP BY over kind instead of eight COUNT queries.
        by_kind = dict(
            unread.values_list('kind').annotate(n=Count('id')).values_list('kind', 'n')
        )

        def count(*kinds):
            return sum(by_kind.get(k, 0) for k in kinds)

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

        snapshot = {
            'recent_notifications': recent,
            'unread_notification_count': unread_total,
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
        snapshot = empty

    setattr(request, _SNAPSHOT_ATTR, snapshot)
    return snapshot


def notification_count(request):
    """Add unread notification count to every template's context."""
    snap = _notification_snapshot(request)
    return {'unread_notification_count': snap['unread_notification_count']}


def recent_notifications_context(request):
    """Add recent (5) notifications + unread count to every template."""
    snap = _notification_snapshot(request)
    return {
        'recent_notifications': snap['recent_notifications'],
        'unread_notification_count': snap['unread_notification_count'],
    }


def notification_sections(request):
    """Per-section and per-link unread notification counts for the sidebar."""
    snap = _notification_snapshot(request)
    return {k: v for k, v in snap.items() if k.startswith('notif_')}


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
