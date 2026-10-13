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
