from django.db import migrations


def backfill(apps, schema_editor):
    """Grandfather any already-closed finding as verified.

    The verification loop forbids closing a finding that was never verified, but
    findings closed before this feature existed have no verification record.
    Mark them verified so the new invariant does not retroactively strand them
    (and so editing one does not fail validation).
    """
    AuditFinding = apps.get_model('audits', 'AuditFinding')
    AuditFinding.objects.filter(status='closed').exclude(
        verification_status='verified'
    ).update(verification_status='verified')


def unbackfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0007_auditfinding_verification_notes_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
