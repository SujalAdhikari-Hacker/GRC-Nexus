from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver
from .models import Control


@receiver(post_save, sender=Control)
def recalc_residuals_on_control_change(sender, instance, **kwargs):
    """When a control's status or effectiveness changes,
    recompute residual scores for every linked risk."""
    from risks.services import recalculate_residual_for_control
    recalculate_residual_for_control(instance)


@receiver(pre_delete, sender=Control)
def cache_risks_before_control_delete(sender, instance, **kwargs):
    """Remember which risks this control mitigated, before the rows are gone.

    Django removes the ``Risk.controls`` through-rows as part of the delete,
    and that does *not* fire ``m2m_changed`` — so by the time ``post_delete``
    runs, ``instance.risks`` is already empty. Stash the PKs on the instance
    so the delete can still trigger a residual recompute.
    """
    instance._grc_risk_pks = list(instance.risks.values_list('pk', flat=True))


@receiver(post_delete, sender=Control)
def recalc_residuals_on_control_delete(sender, instance, **kwargs):
    """Deleting a control must raise the residual of every risk it mitigated.

    Without this the risk kept a stale, reassuringly low residual and no
    appetite breach was ever raised — the worst kind of GRC bug, because it is
    silently wrong in the *safe-looking* direction.
    """
    from risks.models import Risk
    from risks.services import recalculate_risk

    risk_pks = getattr(instance, '_grc_risk_pks', None) or []
    for risk in Risk.objects.filter(pk__in=risk_pks).prefetch_related('controls'):
        recalculate_risk(risk)
