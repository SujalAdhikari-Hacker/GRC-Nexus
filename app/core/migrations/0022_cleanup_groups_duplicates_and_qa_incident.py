"""Align HOD/Staff group permissions, deduplicate seeded laptops, and clear leftover QA incident."""
from django.db import migrations


def cleanup_groups_duplicates_and_qa_incident(apps, schema_editor):
    # 1. Strip Django admin permissions from Department Staff so Staff never
    #    holds more Django permissions than Department HODs.
    try:
        Group = apps.get_model('auth', 'Group')
        User = apps.get_model('core', 'User')
        staff_group = Group.objects.filter(name='Department Staff').first()
        hod_group = Group.objects.filter(name='Department HODs').first()

        if staff_group is not None:
            admin_perms = list(
                staff_group.permissions.filter(content_type__app_label='admin')
            )
            if admin_perms:
                staff_group.permissions.remove(*admin_perms)

        if hod_group is not None:
            for hod in User.objects.filter(is_hod=True, is_superuser=False):
                hod.groups.add(hod_group)
                if staff_group is not None:
                    hod.groups.remove(staff_group)
    except LookupError:
        pass

    # 2. Deduplicate identical seeded "Employee Laptops" assets in Operations.
    try:
        Asset = apps.get_model('assets', 'Asset')
        dupes = list(
            Asset.objects.filter(
                name='Employee Laptops', owner_dept__name='Operations'
            ).order_by('pk')
        )
        if len(dupes) > 1:
            keeper = dupes[0]
            for extra in dupes[1:]:
                try:
                    for risk in extra.risks.all():
                        keeper.risks.add(risk)
                    for policy in extra.policies.all():
                        keeper.policies.add(policy)
                    for inc in extra.incidents.all():
                        keeper.incidents.add(inc)
                    for finding in list(extra.findings.all()):
                        if not keeper.findings.filter(
                            vulnerability=finding.vulnerability, port=finding.port
                        ).exists():
                            finding.asset = keeper
                            finding.save(update_fields=['asset'])
                        else:
                            finding.delete()
                    extra.delete()
                except Exception:
                    # Leave any row that cannot be cleanly removed untouched.
                    pass
    except LookupError:
        pass

    # 3. Remove leftover closed QA test incident (INC-2026-0001 with blank root cause).
    try:
        Incident = apps.get_model('incidents', 'Incident')
        from django.db.models import Q

        Incident.objects.filter(
            reference='INC-2026-0001', status='closed',
        ).filter(
            Q(root_cause='') | Q(title__icontains='QA')
        ).delete()
    except LookupError:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0021_historicaluser_session_nonce_user_session_nonce'),
        ('guardian', '__latest__'),
        ('assets', '__latest__'),
        ('incidents', '__latest__'),
        ('auth', '__latest__'),
    ]

    operations = [
        migrations.RunPython(
            cleanup_groups_duplicates_and_qa_incident, migrations.RunPython.noop
        ),
    ]
