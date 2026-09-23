from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Control


@receiver(post_save, sender=Control)
def recalc_residuals_on_control_change(sender, instance, **kwargs):
    """When a control's status or effectiveness changes,
    recompute residual scores for every linked risk."""
    from risks.services import recalculate_residual_for_control
    recalculate_residual_for_control(instance)