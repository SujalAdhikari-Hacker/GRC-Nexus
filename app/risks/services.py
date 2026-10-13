"""
Business logic for the cascade engine.

Any change to an Asset, Control, or Risk that should ripple through
the data model goes through a function here. Signals call these functions.
Views call these functions. Never put logic in signals or views directly.
"""


def calculate_residual_score(risk):
    """
    Residual = inherent × (1 - average effectiveness of implemented controls).

    Effectiveness is stored as a numeric score 0-5
    (0=not tested, 1=ineffective, 3=partially effective, 5=effective).
    If no implemented controls exist, residual equals inherent.
    """
    controls = list(risk.controls.filter(status='implemented'))
    if not controls:
        return risk.inherent_score

    avg_effectiveness = sum(c.effectiveness for c in controls) / (len(controls) * 5.0)
    residual = round(risk.inherent_score * (1 - avg_effectiveness))
    return max(0, min(25, residual))


def find_applicable_appetite(risk):
    """
    Return the most specific RiskAppetite applicable to this risk.

    Order of precedence (most specific first):
      1. Department + Category
      2. Department only
      3. Category only
      4. Org-wide (no department, no category)

    Returns None if no appetite exists.
    """
    from .models import RiskAppetite

    department = risk.owner_dept
    category = risk.category

    # Build the candidate list from most specific to least
    candidates = []
    if department_id := (department.pk if department else None):
        if category:
            candidates.append(
                RiskAppetite.objects.filter(department_id=department_id, category=category).first()
            )
        candidates.append(
            RiskAppetite.objects.filter(department_id=department_id, category__isnull=True).first()
        )
    if category:
        candidates.append(
            RiskAppetite.objects.filter(department__isnull=True, category=category).first()
        )
    candidates.append(
        RiskAppetite.objects.filter(department__isnull=True, category__isnull=True).first()
    )

    for c in candidates:
        if c is not None:
            return c
    return None


def check_appetite_breach(risk):
    """True if residual score exceeds the applicable appetite's max_residual_score."""
    appetite = find_applicable_appetite(risk)
    if not appetite:
        return False
    return risk.residual_score > appetite.max_residual_score


def recalculate_risk(risk):
    """
    Recompute residual score and appetite breach flag.

    Uses .update() instead of .save() to avoid recursion through the
    post_save signal.
    """
    from .models import Risk

    # Step 1: recompute residual
    residual = calculate_residual_score(risk)
    Risk.objects.filter(pk=risk.pk).update(residual_score=residual)
    risk.refresh_from_db()

    # Step 2: recompute appetite breach with the fresh residual
    breached = check_appetite_breach(risk)
    Risk.objects.filter(pk=risk.pk).update(appetite_breached=breached)
    risk.refresh_from_db()

    return risk


def recalculate_residual_for_control(control):
    """Called when a control is saved — recompute residual for every linked risk."""
    for risk in control.risks.all():
        recalculate_risk(risk)


def recalculate_breaches_for_appetite(appetite):
    """
    Called when a RiskAppetite is saved — recompute the breach flag for
    every risk whose applicable appetite is this one.

    This means editing an appetite immediately updates all affected risks,
    without waiting for them to be saved again.
    """
    from .models import Risk

    risks = Risk.objects.all()
    if appetite.department_id:
        risks = risks.filter(owner_dept_id=appetite.department_id)
    if appetite.category_id:
        risks = risks.filter(category_id=appetite.category_id)

    for risk in risks:
        # Only recompute if this appetite is the one that wins for this risk
        if find_applicable_appetite(risk) == appetite:
            breached = check_appetite_breach(risk)
            Risk.objects.filter(pk=risk.pk).update(appetite_breached=breached)


def create_baseline_risk_for_asset(asset):
    """
    CASCADE #1: When an asset is created, auto-generate a baseline risk entry.
    """
    from .models import Risk, RiskCategory

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
        impact=asset.criticality,
        status='identified',
        treatment_strategy='mitigate',
    )
    risk.assets.add(asset)
    recalculate_risk(risk)
    return risk