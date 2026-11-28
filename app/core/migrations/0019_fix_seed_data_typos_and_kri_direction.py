from django.db import migrations
from django.utils import timezone


def fix_seed_data_and_kri_direction(apps, schema_editor):
    try:
        KRI = apps.get_model('kris', 'KRI')
    except LookupError:
        KRI = None

    if KRI is not None:
        fixed_kris = list(
            KRI.objects.filter(name='Critical patch SLA (7 days)', direction='higher_worse')
        )
        for kri in fixed_kris:
            kri.direction = 'higher_better'
            kri.save(update_fields=['direction'])
            if kri.current_value > kri.red_threshold:
                try:
                    ContentType = apps.get_model('contenttypes', 'ContentType')
                    Ticket = apps.get_model('tickets', 'Ticket')
                    ct = ContentType.objects.filter(app_label='kris', model='kri').first()
                    if ct is not None:
                        Ticket.objects.filter(
                            content_type=ct,
                            object_id=kri.pk,
                            source='alert',
                            status__in=['open', 'assigned', 'in_progress', 'blocked'],
                        ).update(
                            status='cancelled',
                            closed_at=timezone.now(),
                            resolution_notes=(
                                'Auto-cancelled after fixing inverted KRI direction on '
                                'Critical patch SLA (7 days).'
                            ),
                        )
                except LookupError:
                    pass

    try:
        Asset = apps.get_model('assets', 'Asset')
        Asset.objects.filter(name='AWS S3 Backup Backet').update(name='AWS S3 Backup Bucket')
    except LookupError:
        pass

    try:
        AuditFinding = apps.get_model('audits', 'AuditFinding')
        AuditFinding.objects.filter(title='SIEM alert tuning gaps2').update(
            title='SIEM alert tuning gaps'
        )
    except LookupError:
        pass

    try:
        Control = apps.get_model('controls', 'Control')
        Control.objects.filter(
            code='CTL-BCP-001',
            status='implemented',
            lifecycle_status='designed',
        ).update(status='planned')
    except LookupError:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_enable_audit_compliance_oversight'),
        ('guardian', '__latest__'),
    ]

    operations = [
        migrations.RunPython(fix_seed_data_and_kri_direction, migrations.RunPython.noop),
    ]
