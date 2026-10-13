from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from frameworks.models import Framework, FrameworkControl, ComplianceAssessment, ComplianceAssessmentItem
from core.models import Department, User


class Command(BaseCommand):
    help = 'Backfill: for each existing ComplianceAssessment, create items for every FrameworkControl'

    @transaction.atomic
    def handle(self, *args, **options):
        total_created = 0
        for assessment in ComplianceAssessment.objects.all():
            existing_fc_ids = set(
                assessment.items.values_list('framework_control_id', flat=True)
            )
            for fc in assessment.framework.controls.all():
                if fc.pk in existing_fc_ids:
                    continue
                ComplianceAssessmentItem.objects.create(
                    assessment=assessment,
                    framework_control=fc,
                    status='not_assessed',
                )
                total_created += 1
        self.stdout.write(self.style.SUCCESS(
            f'Created {total_created} new items across existing assessments.'
        ))
