"""
Instant alert signals — fire immediately when a critical event happens,
rather than waiting for the next scan_for_alerts run.

Handles: risk appetite breach (immediate).
Everything else (overdue, KEV sync, etc.) is handled by scan_for_alerts.
"""
from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver


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