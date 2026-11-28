"""Tests for vendor list filtering (regression: tier is an integer column)."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Department, User

from .forms import VendorAssessmentForm
from .models import Vendor, VendorAssessment


class VendorFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Vendor Dept')
        cls.user = User.objects.create_user(
            'vendor_user', 'vendor@example.com', 'pw', department=cls.dept,
        )
        cls.critical = Vendor.objects.create(
            name='Critical Co', service='cloud', tier=1, status='active',
            owner_dept=cls.dept,
        )
        cls.standard = Vendor.objects.create(
            name='Standard Co', service='saas', tier=3, status='suspended',
            owner_dept=cls.dept,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _names(self, response):
        return {v.name for v in response.context['vendors']}

    def test_tier_filter_matches_integer_column(self):
        response = self.client.get(reverse('vendors:list'), {'tier': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), {'Critical Co'})

    def test_other_filters_still_work(self):
        response = self.client.get(reverse('vendors:list'), {'service': 'saas'})
        self.assertEqual(self._names(response), {'Standard Co'})

        response = self.client.get(reverse('vendors:list'), {'status': 'active'})
        self.assertEqual(self._names(response), {'Critical Co'})

    def test_invalid_filter_values_are_rejected(self):
        for params in (
            {'tier': '4'},
            {'tier': 'critical'},
            {'service': 'not-a-service'},
            {'status': 'not-a-status'},
        ):
            with self.subTest(params=params):
                response = self.client.get(reverse('vendors:list'), params)
                self.assertEqual(response.status_code, 400)


class VendorAssessmentScaleAndOverdueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Vendor Scale Dept')
        cls.user = User.objects.create_user(
            'scale_user', 'scale@example.com', 'pw', department=cls.dept,
        )
        cls.vendor = Vendor.objects.create(
            name='Expired Co', service='cloud', tier=1, status='active',
            owner_dept=cls.dept, contact_name='Contact',
            contract_renewal_date=date.today() - timedelta(days=10),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_max_dimensions_sum_to_100(self):
        assessment = VendorAssessment.objects.create(
            vendor=self.vendor,
            security_score=20,
            compliance_score=20,
            financial_score=20,
            reputation_score=20,
            operational_score=20,
            assessment_date=date.today(),
            key_findings='Detailed assessment findings for the test vendor.',
            recommended_mitigation='Detailed mitigation plan for the test vendor.',
        )
        self.assertEqual(float(assessment.overall_score), 100.0)
        self.assertEqual(assessment.overall_risk_rating, 'critical')

    def test_dimension_above_20_rejected(self):
        assessment = VendorAssessment(
            vendor=self.vendor,
            security_score=25,
            compliance_score=10,
            financial_score=10,
            reputation_score=10,
            operational_score=10,
            assessment_date=date.today(),
            key_findings='Detailed assessment findings for the test vendor.',
            recommended_mitigation='Detailed mitigation plan for the test vendor.',
        )
        with self.assertRaises(ValidationError):
            assessment.full_clean()

        form = VendorAssessmentForm(data={
            'vendor': self.vendor.pk,
            'vendor_tier': 1,
            'security_score': 25,
            'compliance_score': 10,
            'financial_score': 10,
            'reputation_score': 10,
            'operational_score': 10,
            'assessment_date': date.today().isoformat(),
            'status': 'completed',
            'key_findings': 'Detailed assessment findings for the test vendor.',
            'recommended_mitigation': 'Detailed mitigation plan for the test vendor.',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('security_score', form.errors)

    def test_expired_contract_days_overdue_is_positive(self):
        self.assertEqual(self.vendor.days_overdue, 10)
        resp = self.client.get(reverse('vendors:list'))
        self.assertContains(resp, '10 days overdue')
        self.assertNotContains(resp, '-10 days overdue')
