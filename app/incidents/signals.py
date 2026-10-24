"""Signal hooks for the incident register.

A new incident raises one notification for its owning department:

* ``incident_open`` — filed automatically on every new incident and cleared
  only when the incident is closed. The bell count therefore reflects live
  operational pressure, exactly like open tickets do.

The 72-hour regulatory clock for personal-data breaches is *not* a
signal — it is watched by the escalation collector in ``core.escalations``,
which emails the handler (or the HOD) with the same idempotency rules as
every other escalation source.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.notifications import create_notification

from .models import Incident


@receiver(post_save, sender='incidents.Incident')
def incident_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    prefix = instance.reference or f'INC-{instance.pk:04d}'
    create_notification(
        'incident_open',
        f'{prefix} [{instance.get_severity_display()}] "{instance.title[:80]}"'
        ' needs triage',
        f'/incidents/{instance.pk}/',
        instance.owner_dept,
        instance,
    )
