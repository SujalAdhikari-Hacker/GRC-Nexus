from django.db import migrations

from core.rls import apply_rls, remove_rls


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0010_historicaluser_must_change_password_and_more'),
    ]

    operations = [
        migrations.RunPython(apply_rls, remove_rls),
    ]
