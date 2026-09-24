"""
Cross-app correlation service.

Given any object in the GRC graph, return everything correlated to it.
"""
from django.db.models import Q


# ------------------------------------------------------------------
# ASSET CORRELATIONS
# ------------------------------------------------------------------

def get_policies_for_asset(asset):
    from policies.models import Policy

    direct_ids = set(asset.policies.values_list('pk', flat=True))
    dept_ids = set(
        Policy.objects.filter(applies_to_departments=asset.owner_dept)
        .values_list('pk', flat=True)
    )
    return Policy.objects.filter(pk__in=direct_ids | dept_ids).distinct()


def get_controls_for_asset(asset):
    from controls.models import Control
    return Control.objects.filter(risks__assets=asset).distinct()


def get_vendors_for_asset(asset):
    return asset.vendors.all()


def get_risks_for_asset(asset):
    return asset.risks.all()


def get_framework_coverage_for_asset(asset):
    from frameworks.models import FrameworkControl
    controls = get_controls_for_asset(asset)
    return FrameworkControl.objects.filter(controls__in=controls).distinct()


def get_full_asset_context(asset):
    return {
        'asset': asset,
        'risks': get_risks_for_asset(asset),
        'controls': get_controls_for_asset(asset),
        'policies': get_policies_for_asset(asset),
        'vendors': get_vendors_for_asset(asset),
        'framework_controls': get_framework_coverage_for_asset(asset),
    }


# ------------------------------------------------------------------
# RISK CORRELATIONS
# ------------------------------------------------------------------

def get_controls_for_risk(risk):
    return risk.controls.all()


def get_assets_for_risk(risk):
    return risk.assets.all()


def get_related_risks(risk):
    from risks.models import Risk
    asset_ids = risk.assets.values_list('pk', flat=True)
    control_ids = risk.controls.values_list('pk', flat=True)
    return (
        Risk.objects.exclude(pk=risk.pk)
        .filter(Q(assets__pk__in=asset_ids) | Q(controls__pk__in=control_ids))
        .distinct()
    )


def get_full_risk_context(risk):
    return {
        'risk': risk,
        'assets': get_assets_for_risk(risk),
        'controls': get_controls_for_risk(risk),
        'treatments': risk.treatments.all(),
        'related_risks': get_related_risks(risk),
    }


# ------------------------------------------------------------------
# CONTROL CORRELATIONS
# ------------------------------------------------------------------

def get_risks_for_control(control):
    return control.risks.all()


def get_assets_for_control(control):
    from assets.models import Asset
    return Asset.objects.filter(risks__controls=control).distinct()


def get_frameworks_for_control(control):
    from frameworks.models import Framework
    return Framework.objects.filter(
        controls__in=control.framework_controls.all()
    ).distinct()


def get_full_control_context(control):
    return {
        'control': control,
        'risks': get_risks_for_control(control),
        'assets': get_assets_for_control(control),
        'framework_controls': control.framework_controls.all(),
        'frameworks': get_frameworks_for_control(control),
        'evidence': control.evidence.all(),
    }


# ------------------------------------------------------------------
# POLICY CORRELATIONS
# ------------------------------------------------------------------

def get_assets_for_policy(policy):
    from assets.models import Asset

    direct_ids = set(policy.assets.values_list('pk', flat=True))
    dept_ids = set(
        Asset.objects.filter(owner_dept__in=policy.applies_to_departments.all())
        .values_list('pk', flat=True)
    )
    return Asset.objects.filter(pk__in=direct_ids | dept_ids).distinct()


def get_full_policy_context(policy):
    return {
        'policy': policy,
        'assets': get_assets_for_policy(policy),
        'departments': policy.applies_to_departments.all(),
    }


# ------------------------------------------------------------------
# VENDOR CORRELATIONS
# ------------------------------------------------------------------

def get_risks_for_vendor(vendor):
    from risks.models import Risk
    asset_ids = vendor.provides_assets.values_list('pk', flat=True)
    return Risk.objects.filter(assets__pk__in=asset_ids).distinct()


def get_full_vendor_context(vendor):
    return {
        'vendor': vendor,
        'assets': vendor.provides_assets.all(),
        'risks': get_risks_for_vendor(vendor),
        'assessments': vendor.assessments.all(),
    }


# ------------------------------------------------------------------
# FRAMEWORK COVERAGE
# ------------------------------------------------------------------

def get_framework_coverage(framework):
    """
    Weighted coverage stats for a framework.
    A requirement is 'covered' if any internal Control maps to it via
    either the legacy M2M or ControlFrameworkMapping.

    Relationship weights:
      equal / superset -> 1.0
      functional_partial -> 0.7
      subset / intersects -> 0.5
    """
    from controls.models import Control, ControlFrameworkMapping

    weights = {
        'equal':              1.0,
        'superset':           1.0,
        'functional_partial': 0.7,
        'subset':             0.5,
        'intersects':         0.5,
    }

    all_fc = list(framework.controls.all())
    total = len(all_fc)

    # Legacy M2M links (implicit full coverage)
    direct_ids = set(
        Control.objects.filter(framework_controls__framework=framework)
        .values_list('framework_controls__pk', flat=True)
    )

    # New mapping model with relationship weights
    mapping_weight = {}
    for m in ControlFrameworkMapping.objects.filter(
        framework_control__framework=framework
    ).select_related('framework_control'):
        fc_id = m.framework_control_id
        w = weights.get(m.relationship, 1.0)
        mapping_weight[fc_id] = max(mapping_weight.get(fc_id, 0), w)

    covered_full = 0
    covered_partial = 0
    weighted = 0.0
    gap = 0

    for fc in all_fc:
        if fc.pk in direct_ids:
            covered_full += 1
            weighted += 1.0
        elif fc.pk in mapping_weight:
            w = mapping_weight[fc.pk]
            weighted += w
            if w >= 1.0:
                covered_full += 1
            else:
                covered_partial += 1
        else:
            gap += 1

    percent = round((weighted / total) * 100) if total else 0

    return {
        'total': total,
        'covered': covered_full + covered_partial,
        'covered_full': covered_full,
        'covered_partial': covered_partial,
        'gap': gap,
        'percent': percent,
    }


def get_control_coverage_by_control_for_framework(framework):
    from controls.models import Control, ControlFrameworkMapping

    rows = []
    for fc in framework.controls.all().order_by('code'):
        direct = Control.objects.filter(framework_controls=fc).distinct()
        mapped = Control.objects.filter(framework_mappings__framework_control=fc).distinct()
        covering = (direct | mapped).distinct()
        rows.append((fc, list(covering)))
    return rows
