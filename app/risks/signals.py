from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from assets.models import Asset
from .models import Risk, RiskAppetite


# ==================================================================
# ASSET → baseline risk + auto-link policies
# ==================================================================

@receiver(post_save, sender=Asset)
def asset_created_cascade(sender, instance, created, **kwargs):
    """CASCADE #1: new asset → baseline risk."""
    if not created:
        return
    from .services import create_baseline_risk_for_asset
    create_baseline_risk_for_asset(instance)


@receiver(post_save, sender=Asset)
def asset_auto_link_policies(sender, instance, created, **kwargs):
    """CASCADE #4: new asset → auto-link to policies that apply to its department."""
    if not created:
        return
    from policies.models import Policy
    dept_policies = Policy.objects.filter(applies_to_departments=instance.owner_dept)
    if dept_policies.exists():
        instance.policies.add(*dept_policies)


# ==================================================================
# RISK → recompute residual + breach on every save
# ==================================================================

@receiver(post_save, sender=Risk)
def risk_saved_recalculate(sender, instance, created, **kwargs):
    """
    CASCADE #2a: every time a Risk is saved, recompute its residual
    and appetite breach flag.

    Safe from recursion: recalculate_risk uses .update(), which does not
    fire post_save.
    """
    from .services import recalculate_risk
    recalculate_risk(instance)


# ==================================================================
# RISK APPETITE → recheck all affected risks
# ==================================================================

@receiver(post_save, sender=RiskAppetite)
def appetite_saved_recalculate_breaches(sender, instance, **kwargs):
    """
    CASCADE #2b: when a RiskAppetite is saved, recompute the breach flag
    for every risk that uses this appetite.

    This ensures editing an appetite immediately updates existing risks —
    without this, you'd have to re-save each risk manually.
    """
    from .services import recalculate_breaches_for_appetite
    recalculate_breaches_for_appetite(instance)


# ==================================================================
# M2M cascades
# ==================================================================

@receiver(m2m_changed, sender=Risk.controls.through)
def risk_controls_changed(sender, instance, action, **kwargs):
    """CASCADE #3: controls attached to a risk → recompute residual + breach."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        from .services import recalculate_risk
        recalculate_risk(instance)


@receiver(m2m_changed, sender=Risk.assets.through)
def risk_assets_changed(sender, instance, action, **kwargs):
    """CASCADE #3b: assets attached to a risk → recompute (assets affect criticality)."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        from .services import recalculate_risk
        recalculate_risk(instance)