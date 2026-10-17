"""
Business logic for the cascade engine.

Any change to an Asset, Control, or Risk that should ripple through the data
model goes through a function here. Signals call these functions; views call
these functions. Keep the logic here, not in signals or views.

--------------------------------------------------------------------------
Residual scoring model
--------------------------------------------------------------------------
Residual risk is inherited risk reduced by *defence in depth*: each
implemented control removes a fraction of what is left, rather than the
control set being averaged (which — used to — let a single 5/5 control take a
25 down to 0, and let adding a weak control *raise* the residual).

    reduction_i = min(MAX_SINGLE_CONTROL_REDUCTION,
                      effectiveness_ratio_i * type_weight_i) × CONTROL_CONFIDENCE
    remaining   = Π (1 − reduction_i)
    residual    = inherent × remaining          (clamped to 1–25 when inherent > 0)

Properties this gives us:

* a single control can never remove more than ~2/3 of a risk (no more
  "one perfect control = zero risk", and no "two perfect controls = zero");
* adding a control can only ever lower the residual, never raise it;
* untested / ineffective controls contribute no reduction;
* overlapping controls compound (defence in depth).

Effective control ratings map to a 0–1 ratio:
    0 = not tested → 0.0, 1 = ineffective → 0.2, 3 = partially → 0.6,
    5 = effective → 1.0.  (See Control.EFFECTIVENESS_SCORES; the ratio is
    ``effectiveness / 5``.)
"""
from django.db.models import Q

# How much of the *remaining* risk each control type is assumed to address,
# at full effectiveness. Preventive controls act before an event, detective
# controls only surface it, corrective controls limit the damage after.
CONTROL_TYPE_WEIGHTS = {
    'preventive': 1.0,
    'detective':  0.7,
    'corrective': 0.8,
}
DEFAULT_TYPE_WEIGHT = 0.8

# No control, however well rated, is credited with removing all of a risk: the
# business process keeps some irreducible residual. This factor (applied after
# the per-type weight) is what stops a single 5/5 control from taking a 25 to 0,
# and what keeps two "perfect" controls from silently zeroing a 16.
CONTROL_CONFIDENCE = 0.75

# Absolute ceiling on any single control's reduction, as a belt-and-braces
# guard in case the weights above are ever edited to >1.
MAX_SINGLE_CONTROL_REDUCTION = 0.9

# A treated risk is never "no risk". Even a large stack of fully effective
# controls leaves an irreducible residual (residual other risks, control
# failure, unknown-unknowns). Without this floor, four perfect preventive
# controls drive a 25 all the way to 0 — which an auditor will (rightly) throw
# back at you. 1 is the floor for any risk whose inherent score is above 0.
RESIDUAL_FLOOR = 1


# ---------------------------------------------------------------------------
# Severity bands — the single source of truth
# ---------------------------------------------------------------------------

# Thresholds on the 1–25 inherent/residual scale (likelihood × impact).
SEVERITY_THRESHOLDS = (
    ('critical', 20),
    ('high',     12),
    ('medium',    6),
    ('low',       0),
)


def severity_band(score):
    """Map a 1–25 risk score to its band name.

    Every register, dashboard, heatmap and report must call this rather than
    hand-rolling ``>= 20`` comparisons — otherwise "High" can mean 12 in one
    screen and 10 in another.
    """
    try:
        score = int(score or 0)
    except (TypeError, ValueError):
        score = 0
    for band, threshold in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return band
    return 'low'


# ---------------------------------------------------------------------------
# Control selection
# ---------------------------------------------------------------------------

def mitigating_controls(controls_qs):
    """Only controls that actually provide assurance right now.

    ``implemented`` is the source of truth; retired controls are excluded even
    if their status was left stale.
    """
    return controls_qs.filter(status='implemented').exclude(lifecycle_status='retired')


def calculate_residual_from_controls(inherent_score, controls):
    """Residual for a given inherent score and an iterable of Control objects."""
    remaining = 1.0
    for control in controls:
        ratio = control.effectiveness_ratio  # 0.0–1.0
        weight = CONTROL_TYPE_WEIGHTS.get(control.control_type, DEFAULT_TYPE_WEIGHT)
        reduction = min(MAX_SINGLE_CONTROL_REDUCTION, ratio * weight) * CONTROL_CONFIDENCE
        remaining *= (1.0 - reduction)

    residual = int(round(inherent_score * remaining))
    residual = max(0, min(25, residual))
    # Floor: a risk that has an inherent score can never be reduced to zero.
    if inherent_score > 0:
        residual = max(RESIDUAL_FLOOR, residual)
    return residual


def calculate_residual_score(risk):
    """Residual score for a saved Risk, based on its implemented controls."""
    controls = list(mitigating_controls(risk.controls.all()))
    if not controls:
        return risk.inherent_score
    return calculate_residual_from_controls(risk.inherent_score, controls)


# ---------------------------------------------------------------------------
# Risk appetite
# ---------------------------------------------------------------------------

def _appetite_candidates(risk):
    """Yield appetite querysets from most specific to least specific."""
    department = risk.owner_dept
    category = risk.category

    if department is not None:
        if category is not None:
            yield Q(department=department, category=category)
        yield Q(department=department, category__isnull=True)
    if category is not None:
        yield Q(department__isnull=True, category=category)
    yield Q(department__isnull=True, category__isnull=True)


def find_applicable_appetite(risk):
    """Return the most specific RiskAppetite for ``risk`` (or None).

    Precedence: department+category → department → category → org-wide.
    Selection is deterministic (ties broken by id) so repeated calls on
    duplicate rows always resolve to the same appetite.
    """
    from .models import RiskAppetite

    for criteria in _appetite_candidates(risk):
        appetite = (
            RiskAppetite.objects.filter(criteria).order_by('id').first()
        )
        if appetite is not None:
            return appetite
    return None


def _breached_for(risk, appetite):
    """True if the risk exceeds the given appetite.

    The *governing* tolerance is the residual ceiling: once a risk has been
    treated, only the residual score should decide whether it is acceptable.
    An **untreated** risk — one whose residual still equals its inherent score
    because no effective control is reducing it — is *also* measured against
    the inherent ceiling, so a fundamentally unacceptable risk stays flagged
    until real mitigation brings the residual down. This is what lets a
    Finance appetite (max_residual=6, max_inherent=10) flag an untreated
    inherent=16 risk and then *clear* it once effective controls drop the
    residual below 6.
    """
    if risk.status == 'closed':
        return False
    if risk.residual_score > appetite.max_residual_score:
        return True
    untreated = risk.residual_score >= risk.inherent_score
    if untreated and risk.inherent_score > appetite.max_inherent_score:
        return True
    return False


def check_appetite_breach(risk):
    """True if the risk breaches its applicable appetite.

    Both the inherent ceiling and the residual tolerance are enforced — the
    inherent score is what the *inherent* appetite field has always described,
    so ignoring it (as the old code did) left half of every appetite unused.
    """
    appetite = find_applicable_appetite(risk)
    if not appetite:
        return False
    return _breached_for(risk, appetite)


# ---------------------------------------------------------------------------
# Recalculation entry points
# ---------------------------------------------------------------------------

def recalculate_risk(risk):
    """Recompute residual score, appetite-breach flag and escalation for a risk.

    Uses ``.update()`` (not ``.save()``) so the post_save signal does not
    recurse.

    Escalation is derived: a risk is escalated when it breaches its appetite
    *and* its residual also exceeds the appetite's ``risk_capacity`` (the point
    beyond which the organisation cannot absorb the loss). This is what gives
    ``RiskAppetite.risk_capacity`` and ``Risk.escalated`` their meaning.
    """
    from django.utils import timezone

    from .models import Risk

    residual = calculate_residual_score(risk)
    # Make the freshly-computed residual visible to _breached_for, which reads
    # risk.residual_score. On create/update the in-memory value is still the
    # pre-save default (0), which would otherwise mask a real breach.
    risk.residual_score = residual
    appetite = find_applicable_appetite(risk)
    breached = _breached_for(risk, appetite) if appetite else False
    escalated = bool(
        breached and appetite and residual > appetite.risk_capacity
    )

    fields = {
        'residual_score': residual,
        'appetite_breached': breached,
        'escalated': escalated,
    }
    if escalated and not risk.escalated:
        fields['escalated_at'] = timezone.now()
        risk.escalated_at = fields['escalated_at']
    elif not escalated:
        fields['escalated_at'] = None
        risk.escalated_at = None

    Risk.objects.filter(pk=risk.pk).update(**fields)
    risk.residual_score = residual
    risk.appetite_breached = breached
    risk.escalated = escalated
    return risk


def recalculate_residual_for_control(control):
    """Recompute residual for every risk linked to a saved control."""
    for risk in control.risks.all().prefetch_related('controls'):
        recalculate_risk(risk)


def sync_risk_from_treatment(treatment):
    """Keep the parent risk consistent with a saved treatment.

    Two long-standing gaps this closes:

    * **Residual recompute** — residual risk is computed from
      ``Risk.controls``, but controls are usually chosen on the *treatment*.
      Without promoting them onto the risk the residual score never moves
      (``Risk.controls.add`` fires the m2m signal that recalculates).
    * **Status sync** — completing the treatment closes the risk, so the
      status no longer has to be updated in two places.
    """
    risk = treatment.risk

    controls = list(treatment.controls.all())
    if controls:
        risk.controls.add(*controls)

    if treatment.status == 'completed' and risk.status != 'closed':
        if risk.can_transition_to('closed'):
            risk.status = 'closed'
            risk.save()

    recalculate_risk(risk)
    return risk


def recalculate_breaches_for_appetite(appetite):
    """Recompute the breach flag for every risk the given appetite could touch.

    Called on appetite *save* **and** *delete*. A single pass loads all
    appetites into memory (one query) and only writes rows whose flag actually
    changes, instead of running a query per risk.
    """
    from .models import Risk, RiskAppetite
    from django.utils import timezone

    risks = Risk.objects.all()
    if appetite.department_id:
        risks = risks.filter(owner_dept_id=appetite.department_id)
    if appetite.category_id:
        risks = risks.filter(category_id=appetite.category_id)
    risks = risks.select_related('category', 'owner_dept')

    # Ordered by id so specificity ties resolve deterministically, matching
    # find_applicable_appetite().
    appetites = list(RiskAppetite.objects.order_by('id'))
    now = timezone.now()

    updates = []
    for risk in risks:
        best = None
        best_rank = 99
        for appetite in appetites:
            if not _appetite_applies(appetite, risk):
                continue
            rank = _specificity_rank(appetite)
            if rank < best_rank:
                best, best_rank = appetite, rank

        breached = _breached_for(risk, best) if best else False
        escalated = bool(
            breached and best and risk.residual_score > best.risk_capacity
        )

        changed = (
            risk.appetite_breached != breached
            or risk.escalated != escalated
        )
        if not changed:
            continue

        risk.appetite_breached = breached
        risk.escalated = escalated
        if escalated and not risk.escalated_at:
            risk.escalated_at = now
        elif not escalated:
            risk.escalated_at = None
        updates.append(risk)

    if updates:
        Risk.objects.bulk_update(
            updates, ['appetite_breached', 'escalated', 'escalated_at']
        )


def _appetite_applies(appetite, risk):
    """True if ``appetite`` is a candidate for ``risk`` (regardless of specificity)."""
    if appetite.department_id and appetite.department_id != risk.owner_dept_id:
        return False
    if appetite.category_id and appetite.category_id != risk.category_id:
        return False
    return True


def _specificity_rank(appetite):
    """Lower is more specific: dept+cat(0) < dept(1) < cat(2) < org(3)."""
    if appetite.department_id and appetite.category_id:
        return 0
    if appetite.department_id:
        return 1
    if appetite.category_id:
        return 2
    return 3


def recompute_all_risks(today=None):
    """Recompute residual + breach for every risk. Used by the maintenance command."""
    from .models import Risk

    count = 0
    for risk in Risk.objects.all().prefetch_related('controls').select_related('category'):
        recalculate_risk(risk)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Asset cascade
# ---------------------------------------------------------------------------

def create_baseline_risk_for_asset(asset):
    """CASCADE #1: a new asset produces one baseline (unassessed) risk.

    Idempotent: re-saving an asset never creates a second baseline for the same
    asset + department.
    """
    from .models import Risk, RiskCategory

    if asset.owner_dept_id is None:
        return None

    existing = Risk.objects.filter(
        title=f"Unassessed risk: {asset.name}",
        owner_dept_id=asset.owner_dept_id,
    ).first()
    if existing:
        return existing

    category, _ = RiskCategory.objects.get_or_create(
        name='Information Security',
        defaults={'description': 'Auto-generated category for asset-derived risks'},
    )

    # Asset criticality (1–4) maps onto the risk impact scale (1–5):
    # low→2, medium→3, high→4, critical→5. A baseline risk never starts at the
    # floor, because an asset worth registering is worth assessing.
    impact = min(5, max(1, (asset.criticality or 1) + 1))

    risk = Risk.objects.create(
        title=f"Unassessed risk: {asset.name}",
        description=(
            f"Auto-generated baseline risk for new asset '{asset.name}'. "
            f"Needs assessment by {asset.owner_dept.name}."
        ),
        category=category,
        owner_dept=asset.owner_dept,
        likelihood=1,
        impact=impact,
        status='identified',
        treatment_strategy='mitigate',
    )
    risk.assets.add(asset)
    recalculate_risk(risk)
    return risk


def resolve_baseline_risk_for_asset(asset, except_risk=None):
    """Close an asset's auto-generated 'Unassessed risk' once a real risk covers it.

    Prevents the register filling with stale placeholders that skew the heatmap,
    counts and appetite checks. Idempotent; safe to call from signals.
    """
    from .models import Risk

    qs = Risk.objects.filter(
        title=f"Unassessed risk: {asset.name}",
        owner_dept_id=asset.owner_dept_id,
    ).exclude(status='closed')
    if except_risk is not None and except_risk.pk:
        qs = qs.exclude(pk=except_risk.pk)

    count = 0
    for risk in qs:
        risk.status = 'closed'
        note = 'Auto-closed: a real risk now covers this asset.'
        risk.closure_notes = f"{risk.closure_notes} {note}".strip() if risk.closure_notes else note
        risk.save(update_fields=['status', 'closed_date', 'closure_notes'])
        count += 1
    return count
