from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Department
from risks.models import Risk, RiskAppetite
from kris.models import KRI, KRIReading


class Command(BaseCommand):
    help = 'Seed demo KRI data'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding KRIs...'))

        depts = {d.name: d for d in Department.objects.all()}
        today = timezone.now().date()

        # (name, category, type, unit, direction, amber, red, frequency, trend, dept, current)
        kri_data = [
            ('Phishing click rate',           'cybersecurity', 'leading',  '%',      'higher_worse',  5,   10,  'monthly',   'stable',     'IT',         7),
            ('Critical patch SLA compliance', 'cybersecurity', 'leading',  '%',      'higher_better', 95,  85,  'weekly',    'increasing', 'IT',         92),
            ('Mean time to detect (MTTD)',    'cybersecurity', 'lagging',  'hours',  'higher_worse',  12,  24,  'monthly',   'decreasing', 'IT',         8),
            ('Mean time to respond (MTTR)',   'cybersecurity', 'lagging',  'hours',  'higher_worse',  48,  72,  'monthly',   'stable',     'IT',         52),
            ('Failed login attempts',         'cybersecurity', 'leading',  'count',  'higher_worse',  500, 1500,'daily',     'increasing', 'IT',         820),
            ('Critical vulnerabilities open', 'technology',    'leading',  'count',  'higher_worse',  5,   15,  'weekly',    'decreasing', 'IT',         4),
            ('Backup success rate',           'technology',    'leading',  '%',      'higher_better', 99,  95,  'daily',     'stable',     'IT',         99.4),
            ('Unpatched systems > 30 days',   'technology',    'leading',  'count',  'higher_worse',  10,  30,  'weekly',    'increasing', 'IT',         18),
            ('Policy review on-time %',       'compliance',    'leading',  '%',      'higher_better', 90,  80,  'quarterly', 'stable',     'Compliance', 93),
            ('Regulatory findings open',      'compliance',    'lagging',  'count',  'higher_worse',  3,   8,   'monthly',   'stable',     'Compliance', 2),
            ('Training completion %',         'people',        'leading',  '%',      'higher_better', 95,  85,  'quarterly', 'increasing', 'HR',         88),
            ('Employee turnover rate',        'people',        'lagging',  '%',      'higher_worse',  12,  20,  'monthly',   'stable',     'HR',         9),
            ('Critical vendor assessments overdue', 'third_party', 'leading', 'count', 'higher_worse', 2, 5, 'monthly', 'stable', 'Compliance', 3),
            ('Vendor high-risk findings',     'third_party',   'lagging',  'count',  'higher_worse',  5,   12,  'monthly',   'increasing', 'Compliance', 7),
            ('Budget variance',               'financial',     'lagging',  '%',      'higher_worse',  5,   15,  'monthly',   'stable',     'Finance',    3),
            ('Fraud incidents',               'financial',     'lagging',  'count',  'higher_worse',  0,   2,   'quarterly', 'stable',     'Finance',    0),
        ]

        created = 0
        for (name, cat, ktype, unit, direction, amber, red, freq, trend, dept_name, current) in kri_data:
            dept = depts.get(dept_name)
            if not dept:
                continue
            kri, was_created = KRI.objects.get_or_create(
                name=name,
                defaults={
                    'category': cat,
                    'kri_type': ktype,
                    'unit': unit,
                    'direction': direction,
                    'amber_threshold': amber,
                    'red_threshold': red,
                    'frequency': freq,
                    'trend': trend,
                    'owner_dept': dept,
                    'current_value': current,
                }
            )
            if was_created:
                created += 1
                # 6 months of readings
                for i in range(6, 0, -1):
                    offset = i * 30
                    # create a plausible history trending toward current
                    factor = (7 - i) / 6.0
                    val = amber * (1 - factor) + float(current) * factor
                    KRIReading.objects.create(
                        kri=kri,
                        reading_date=today - timedelta(days=offset),
                        value=round(val, 2),
                        notes='Auto-generated demo reading.',
                    )
                self.stdout.write(f"  KRI: {name}")

        self.stdout.write(self.style.SUCCESS(f'\n✔ KRI seed complete. Created {created} KRIs.'))
        self.stdout.write(f"  Total KRIs:     {KRI.objects.count()}")
        self.stdout.write(f"  Total readings: {KRIReading.objects.count()}")
