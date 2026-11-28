"""
Instant alert signals — fire immediately when a critical event happens,
rather than waiting for the next scan_for_alerts run.

Handles: risk appetite breach (immediate).
Everything else (overdue, KEV sync, etc.) is handled by scan_for_alerts.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender='risks.Risk')
def on_risk_saved(sender, instance, **kwargs):
    """Fire an instant ticket when a risk's appetite breach flag flips to True."""
    if not instance.appetite_breached:
        return
    if instance.status == 'closed':
        return

    from .alerts import _create_ticket, _open_ticket_exists

    if _open_ticket_exists(instance):
        return

    try:
        _create_ticket({
            'obj': instance,
            'title': f'Risk appetite breach: {instance.title[:80]}',
            'description': (
                f'Risk "{instance.title}" has a residual score of {instance.residual_score} '
                f'which exceeds the appetite threshold.\n\n'
                f'Owner department: {instance.owner_dept.name}\n'
                f'Inherent: {instance.inherent_score} · Residual: {instance.residual_score}'
            ),
            'priority': 4 if instance.inherent_score >= 20 else 3,
            'dept': instance.owner_dept,
        })
    except Exception:
        # Never let an alert failure break a save
        pass


@receiver(post_delete, sender='risks.Risk')
@receiver(post_delete, sender='vulnerabilities.Finding')
@receiver(post_delete, sender='controls.Control')
@receiver(post_delete, sender='kris.KRI')
@receiver(post_delete, sender='audits.ActionItem')
@receiver(post_delete, sender='audits.AuditFinding')
@receiver(post_delete, sender='audits.EvidenceItem')
@receiver(post_delete, sender='vendors.Vendor')
@receiver(post_delete, sender='policies.Policy')
def cancel_alert_tickets_on_delete(sender, instance, **kwargs):
    """Cancel open alert tickets whose linked source record was deleted."""
    if not instance.pk:
        return
    try:
        from .models import Ticket

        ct = ContentType.objects.get_for_model(sender)
        Ticket.objects.filter(
            content_type=ct,
            object_id=instance.pk,
            source='alert',
            status__in=['open', 'assigned', 'in_progress', 'blocked'],
        ).update(
            status='cancelled',
            closed_at=timezone.now(),
            resolution_notes=f'Auto-cancelled because linked {sender._meta.verbose_name} record was deleted.',
        )
    except Exception:
        pass