from django.db import migrations
from django.db.models import Q


def enable_audit_compliance_oversight(apps, schema_editor):
    Department = apps.get_model('core', 'Department')
    Department.objects.filter(
        Q(name__icontains='audit') | Q(name__icontains='compliance')
    ).update(has_org_read_oversight=True)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0017_department_has_org_read_oversight_and_more'),
    ]

    operations = [
        migrations.RunPython(enable_audit_compliance_oversight, migrations.RunPython.noop),
    ]
