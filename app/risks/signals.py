from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from assets.models import Asset
from .models import Risk


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


@receiver(m2m_changed, sender=Risk.controls.through)
def risk_controls_changed(sender, instance, action, **kwargs):
    """CASCADE #2: controls attached to a risk → recompute residual."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        from .services import recalculate_risk
        recalculate_risk(instance)


@receiver(m2m_changed, sender=Risk.assets.through)
def risk_assets_changed(sender, instance, action, **kwargs):
    """CASCADE #3: assets attached to a risk → hook for future logic."""
    pass