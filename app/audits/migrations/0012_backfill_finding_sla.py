from datetime import timedelta

from django.db import migrations
from django.utils import timezone

SLA_DAYS = {'critical': 7, 'high': 14, 'medium': 30, 'low': 60, 'none': 90}


def backfill_finding_sla(apps, schema_editor):
    """Give findings created before the SLA clock a severity-based due date."""
    AuditFinding = apps.get_model('audits', 'AuditFinding')
    for finding in AuditFinding.objects.filter(due_date__isnull=True).iterator():
        start = (
            finding.created_at.date() if finding.created_at
            else timezone.localdate()
        )
        days = SLA_DAYS.get(finding.severity, SLA_DAYS['none'])
        finding.due_date = start + timedelta(days=days)
        finding.save(update_fields=['due_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0011_evidenceversion'),
    ]

    operations = [
        migrations.RunPython(backfill_finding_sla, migrations.RunPython.noop),
    ]
