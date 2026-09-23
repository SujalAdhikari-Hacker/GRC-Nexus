"""
Cross-app correlation service.

Given any object in the GRC graph, return everything correlated to it.
This is the read-side of the cascade engine — cascade writes, correlation reads.
"""
from django.db.models import Q


# ------------------------------------------------------------------
# ASSET CORRELATIONS
# ------------------------------------------------------------------

def get_policies_for_asset(asset):
    """Policies directly linked + policies of the asset's owner department."""
    from policies.models import Policy

    direct_ids = set(asset.policies.values_list('pk', flat=True))
    dept_ids = set(
        Policy.objects.filter(applies_to_departments=asset.owner_dept)
        .values_list('pk', flat=True)
    )
    return Policy.objects.filter(pk__in=direct_ids | dept_ids).distinct()


def get_controls_for_asset(asset):
    """Controls that mitigate risks affecting this asset (indirect)."""
    from controls.models import Control
    return Control.objects.filter(risks__assets=asset).distinct()


def get_vendors_for_asset(asset):
    """Vendors that supply/host/support this asset."""
    return asset.vendors.all()


def get_risks_for_asset(asset):
    """Risks directly linked to this asset."""
    return asset.risks.all()


def get_framework_coverage_for_asset(asset):
    """All framework controls satisfied by any control protecting this asset."""
    from frameworks.models import FrameworkControl
    controls = get_controls_for_asset(asset)
    return FrameworkControl.objects.filter(controls__in=controls).distinct()


def get_full_asset_context(asset):
    """Bundle everything related to an asset."""
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
    """Other risks sharing at least one asset or control with this one."""
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
    """Assets directly linked + assets of departments this policy applies to."""
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
    """Risks affecting any asset supplied by this vendor."""
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
    Returns dict with total controls in the framework, how many are
    satisfied by at least one internal control, and coverage percent.
    """
    from controls.models import Control

    all_fc = framework.controls.all()
    total = all_fc.count()

    # A FrameworkControl is "covered" if any internal Control maps to it
    covered_ids = set(
        Control.objects.filter(framework_controls__framework=framework)
        .values_list('framework_controls__pk', flat=True)
    )
    covered = len(covered_ids)
    percent = round(covered / total * 100) if total else 0

    return {
        'total': total,
        'covered': covered,
        'gap': total - covered,
        'percent': percent,
    }


def get_control_coverage_by_control_for_framework(framework):
    """
    For a framework, return list of (FrameworkControl, [Control, ...])
    so templates can show which internal control covers each requirement.
    """
    from controls.models import Control

    rows = []
    for fc in framework.controls.all().order_by('code'):
        covering = Control.objects.filter(framework_controls=fc).distinct()
        rows.append((fc, list(covering)))
    return rows