from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from assets.models import Asset

from .models import Risk, RiskAppetite


# ==================================================================
# ASSET → baseline risk + auto-link policies
# ==================================================================

@receiver(post_save, sender=Asset)
def asset_created_cascade(sender, instance, created, **kwargs):
    """CASCADE #1: a new asset receives a baseline (unassessed) risk."""
    if not created:
        return
    from .services import create_baseline_risk_for_asset
    create_baseline_risk_for_asset(instance)


@receiver(post_save, sender=Asset)
def asset_auto_link_policies(sender, instance, created, **kwargs):
    """CASCADE #4: a new asset is linked to policies applying to its department."""
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
    """CASCADE #2a: recompute residual + appetite breach whenever a Risk saves.

    Safe from recursion: recalculate_risk() writes with .update(), which does
    not fire post_save.
    """
    from .services import recalculate_risk
    recalculate_risk(instance)


# ==================================================================
# RISK APPETITE → recheck affected risks on save AND delete
# ==================================================================

@receiver(post_save, sender=RiskAppetite)
def appetite_saved_recalculate_breaches(sender, instance, **kwargs):
    """CASCADE #2b: editing an appetite immediately re-flags existing risks."""
    from .services import recalculate_breaches_for_appetite
    recalculate_breaches_for_appetite(instance)


@receiver(post_delete, sender=RiskAppetite)
def appetite_deleted_recalculate_breaches(sender, instance, **kwargs):
    """Deleting an appetite must clear (or re-point) the breach flags it drove.

    Without this, risks stayed flagged as breaching an appetite that no longer
    existed.
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
def risk_assets_changed(sender, instance, action, pk_set, **kwargs):
    """CASCADE #5: linking a real risk to an asset retires the placeholder risk.

    Keeps exactly one live baseline per asset instead of accumulating
    auto-generated 'Unassessed risk' rows.
    """
    if action == 'post_add' and pk_set:
        from assets.models import Asset
        from .services import resolve_baseline_risk_for_asset
        for asset in Asset.objects.filter(pk__in=pk_set):
            resolve_baseline_risk_for_asset(asset, except_risk=instance)
