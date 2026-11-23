"""NIS2 Article 23 deadline sweep.

Run hourly (or more often) from cron::

    python manage.py sweep_nis2_deadlines

For every significant, open incident the sweep checks the three phase clocks
and raises at most one pre-deadline and one breach alert per phase. Deduping
is enforced by :class:`incidents.models.Nis2DeadlineAlert`'s unique
constraint, not by memory, so repeated runs and concurrent workers cannot
notify twice. In-app notifications (and email, where enabled) go to the
handler and the owning department.
"""
from django.urls import reverse
from django.utils import timezone

from core.notifications import create_notification

from .models import Incident, Nis2DeadlineAlert
from .nis2 import phase_clocks


def sweep_deadlines(now=None, dry_run=False):
    """Dispatch due-soon and breach alerts; return a summary.

    ``dry_run`` reports what would fire without writing alerts or
    notifications.
    """
    now = now or timezone.now()
    incidents = list(
        Incident.objects.filter(nis2_significant=True)
        .exclude(status='closed')
        .select_related('owner_dept', 'handler')
    )

    dispatched = []
    for incident in incidents:
        for clock in phase_clocks(
            incident.detected_at, incident.nis2_submissions, now
        ):
            if clock.state not in ('due_soon', 'breached'):
                continue

            kind = 'breach' if clock.state == 'breached' else 'pre_deadline'
            entry = {
                'reference': incident.reference,
                'phase': clock.phase,
                'kind': kind,
            }
            if dry_run:
                dispatched.append(entry)
                continue

            _alert, created = Nis2DeadlineAlert.objects.get_or_create(
                incident=incident, phase=clock.phase, kind=kind,
            )
            if not created:
                continue

            if kind == 'breach':
                notification_kind = 'incident_nis2_breach'
                title = (
                    f'NIS2 Art. 23: {incident.reference} missed the '
                    f'{clock.label.lower()} deadline'
                )
            else:
                notification_kind = 'incident_nis2_due'
                title = (
                    f'NIS2 Art. 23: {incident.reference} '
                    f'{clock.label.lower()} due in {clock.remaining_label}'
                )

            create_notification(
                kind=notification_kind,
                title=title,
                action_url=reverse('incidents:detail', args=[incident.pk]),
                owner_dept=incident.owner_dept,
                ref_obj=incident,
                recipient=incident.handler,
            )
            dispatched.append(entry)

    return {'scanned': len(incidents), 'dispatched': dispatched}
