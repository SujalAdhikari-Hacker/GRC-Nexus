"""
Business logic for the cascade engine.

Any change to an Asset, Control, or Risk that should ripple through
the data model goes through a function here. Signals call these functions.
Views call these functions. Never put logic in signals or views directly.
"""
from django.db.models import Q


def calculate_residual_score(risk):
    """Residual = inherent × (1 - average effectiveness of implemented controls)."""
    controls = list(risk.controls.filter(status='implemented'))
    if not controls:
        return risk.inherent_score
    avg_effectiveness = sum(c.effectiveness for c in controls) / (len(controls) * 5.0)
    residual = round(risk.inherent_score * (1 - avg_effectiveness))
    return max(0, min(25, residual))


def check_appetite_breach(risk):
    """True if residual score exceeds the applicable appetite threshold."""
    from .models import RiskAppetite

    # Most specific first: dept + category → dept only → category only → org-wide
    appetite = (
        RiskAppetite.objects.filter(department=risk.owner_dept, category=risk.category).first()
        or RiskAppetite.objects.filter(department=risk.owner_dept, category__isnull=True).first()
        or RiskAppetite.objects.filter(department__isnull=True, category=risk.category).first()
        or RiskAppetite.objects.filter(department__isnull=True, category__isnull=True).first()
    )
    if not appetite:
        return False
    return risk.residual_score > appetite.max_residual_score


def recalculate_risk(risk):
    """Recompute residual score and appetite flag. Uses .update() to avoid signal recursion."""
    from .models import Risk

    residual = calculate_residual_score(risk)
    Risk.objects.filter(pk=risk.pk).update(
        residual_score=residual,
    )
    risk.refresh_from_db()
    breached = check_appetite_breach(risk)
    Risk.objects.filter(pk=risk.pk).update(appetite_breached=breached)
    risk.refresh_from_db()


def recalculate_residual_for_control(control):
    """Called when a control is saved — recompute residual for every linked risk."""
    for risk in control.risks.all():
        recalculate_risk(risk)


def create_baseline_risk_for_asset(asset):
    """
    CASCADE #1: When an asset is created, auto-generate a baseline risk entry.
    This is the 'auto-update when asset is added' feature.
    """
    from .models import Risk, RiskCategory

    # Don't duplicate if a baseline already exists
    existing = Risk.objects.filter(
        title=f"Unassessed risk: {asset.name}",
        owner_dept=asset.owner_dept,
    ).first()
    if existing:
        return existing

    category, _ = RiskCategory.objects.get_or_create(
        name='Information Security',
        defaults={'description': 'Auto-generated category for asset-derived risks'},
    )

    risk = Risk.objects.create(
        title=f"Unassessed risk: {asset.name}",
        description=(
            f"Auto-generated baseline risk for new asset '{asset.name}'. "
            f"Needs assessment by {asset.owner_dept.name}."
        ),
        category=category,
        owner_dept=asset.owner_dept,
        likelihood=1,
        impact=asset.criticality,   # inherit asset criticality as initial impact
        status='identified',
        treatment_strategy='mitigate',
    )
    risk.assets.add(asset)
    recalculate_risk(risk)
    return risk