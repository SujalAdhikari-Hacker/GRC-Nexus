from datetime import timedelta

from django.db import migrations
from django.utils import timezone

PRIORITY_DAYS = {4: 7, 3: 14, 2: 30, 1: 60}


def backfill_ticket_sla(apps, schema_editor):
    """Give tickets created before the SLA clock a priority-based due date."""
    Ticket = apps.get_model('tickets', 'Ticket')
    for ticket in Ticket.objects.filter(due_date__isnull=True).iterator():
        start = (
            ticket.created_at.date() if ticket.created_at
            else timezone.localdate()
        )
        days = PRIORITY_DAYS.get(ticket.priority, 30)
        ticket.due_date = start + timedelta(days=days)
        ticket.save(update_fields=['due_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill_ticket_sla, migrations.RunPython.noop),
    ]
