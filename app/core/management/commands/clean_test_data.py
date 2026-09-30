"""
Delete all [TEST]-prefixed data from every app. Keeps users, departments,
frameworks, categories, and any real (non-TEST) records.

Usage:
    docker compose exec web python manage.py clean_test_data
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import User
from assets.models import Asset
from vendors.models import Vendor, VendorAssessment
from policies.models import Policy
from controls.models import Control, ControlFrameworkMapping
from frameworks.models import ComplianceAssessment, ComplianceAssessmentItem
from risks.models import Risk, RiskAppetite, RiskTreatment, RiskException
from kris.models import KRI, KRIReading
from vulnerabilities.models import Vulnerability, Finding as VulnFinding
from audits.models import (
    Audit, AuditFinding, ActionItem, EvidenceItem, EvidenceScore, ControlTest,
)
from threatintel.models import ThreatActor, IOC


TEST = '[TEST]'
CODE = 'TEST-'


class Command(BaseCommand):
    help = 'Delete all [TEST]-prefixed data across every app.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Cleaning TEST data...\n')

        # Children first to avoid FK restrictions
        deleted = {
            'ActionItem':          ActionItem.objects.filter(title__startswith=TEST).delete()[0],
            'AuditFinding':        AuditFinding.objects.filter(title__startswith=TEST).delete()[0],
            'EvidenceScore':       EvidenceScore.objects.filter(evidence__title__startswith=TEST).delete()[0],
            'EvidenceItem':        EvidenceItem.objects.filter(title__startswith=TEST).delete()[0],
            'ControlTest':         ControlTest.objects.filter(control__code__startswith=CODE).delete()[0],
            'Audit':               Audit.objects.filter(name__startswith=TEST).delete()[0],

            'VulnFinding':         VulnFinding.objects.filter(vulnerability__title__startswith=TEST).delete()[0],
            'Vulnerability':       Vulnerability.objects.filter(title__startswith=TEST).delete()[0],

            'ComplianceAssessmentItem': ComplianceAssessmentItem.objects.filter(assessment__name__startswith=TEST).delete()[0],
            'ComplianceAssessment':     ComplianceAssessment.objects.filter(name__startswith=TEST).delete()[0],

            'ControlFrameworkMapping':  ControlFrameworkMapping.objects.filter(control__code__startswith=CODE).delete()[0],

            'RiskException':       RiskException.objects.filter(title__startswith=TEST).delete()[0],
            'RiskTreatment':       RiskTreatment.objects.filter(risk__title__startswith=TEST).delete()[0],
            'Risk':                Risk.objects.filter(title__startswith=TEST).delete()[0],
            'RiskAppetite':        RiskAppetite.objects.filter(description__startswith=TEST).delete()[0],

            'KRIReading':          KRIReading.objects.filter(kri__name__startswith=TEST).delete()[0],
            'KRI':                 KRI.objects.filter(name__startswith=TEST).delete()[0],

            'Control':             Control.objects.filter(code__startswith=CODE).delete()[0],
            'Policy':              Policy.objects.filter(code__startswith=CODE).delete()[0],

            'VendorAssessment':    VendorAssessment.objects.filter(vendor__name__startswith=TEST).delete()[0],
            'Vendor':              Vendor.objects.filter(name__startswith=TEST).delete()[0],
            'Asset':               Asset.objects.filter(name__startswith=TEST).delete()[0],

            'IOC':                 IOC.objects.filter(value__startswith=CODE).delete()[0],
            'ThreatActor':         ThreatActor.objects.filter(name__startswith=TEST).delete()[0],

            'test_user':           User.objects.filter(username='test_user').delete()[0],
        }

        self.stdout.write(self.style.MIGRATE_HEADING('Deleted:'))
        for model, count in deleted.items():
            if count:
                self.stdout.write(f'  {model:<26} {count}')

        self.stdout.write(self.style.SUCCESS('\n✔ Cleanup complete. Users, departments, frameworks, categories preserved.'))