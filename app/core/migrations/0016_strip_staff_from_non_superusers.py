from django.db import migrations


def strip_staff_from_non_superusers(apps, schema_editor):
    User = apps.get_model('core', 'User')
    User.objects.filter(is_superuser=False, is_staff=True).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0015_servicerun'),
    ]

    operations = [
        migrations.RunPython(strip_staff_from_non_superusers, migrations.RunPython.noop),
    ]
