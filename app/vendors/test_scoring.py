"""Tests for supplier assurance scoring — NIS2 Art. 18 / Art. 21(2)(d)."""
from datetime import date, timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Department, User

from .forms import VendorForm
from .models import Vendor, VendorAssessment
from .services import (
    CERTIFICATION_POINTS,
    band_for_score,
    score_vendor,
)

TODAY = date(2026, 3, 1)


def make_vendor(**overrides):
    data = dict(
        certifications=[],
        jurisdiction='unknown',
        security_clauses=False,
        audit_rights=False,
        sla_defined=False,
        breach_notification_hours=None,
        contract_renewal_date=None,
        data_sensitivity=0,
        tier=3,
        last_assessment_date=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def component(score, key):
    return next(c for c in score.components if c.key == key)


class VendorScoreFormulaTests(SimpleTestCase):
    def test_full_marks_is_100_and_low_risk(self):
        score = score_vendor(make_vendor(
            certifications=[
                'ISO27001', 'SOC2', 'PCIDSS', 'ISO22301', 'CSA-STAR',
                'TISAX', 'ISO9001',
            ],
            jurisdiction='eu',
            security_clauses=True,
            audit_rights=True,
            sla_defined=True,
            breach_notification_hours=24,
            data_sensitivity=0,
            last_assessment_date=TODAY - timedelta(days=30),
        ), today=TODAY)
        self.assertEqual(score.score, 100)
        self.assertEqual(score.band, 'low')
        self.assertEqual(score.flags, ())

    def test_certifications_are_capped_at_25(self):
        score = score_vendor(make_vendor(
            certifications=['ISO27001', 'SOC2', 'PCIDSS', 'TISAX'],
        ), today=TODAY)
        self.assertEqual(component(score, 'certifications').awarded, 25)

    def test_unknown_certification_earns_nothing(self):
        score = score_vendor(make_vendor(certifications=['MADE-UP']), today=TODAY)
        self.assertEqual(component(score, 'certifications').awarded, 0)

    def test_duplicate_certifications_count_once(self):
        score = score_vendor(make_vendor(
            certifications=['ISO27001', 'ISO27001', 'SOC2'],
        ), today=TODAY)
        self.assertEqual(
            component(score, 'certifications').awarded,
            CERTIFICATION_POINTS['ISO27001'] + CERTIFICATION_POINTS['SOC2'],
        )

    def test_expired_contract_zeroes_contract_component(self):
        score = score_vendor(make_vendor(
            security_clauses=True, audit_rights=True, sla_defined=True,
            breach_notification_hours=12,
            contract_renewal_date=TODAY - timedelta(days=1),
        ), today=TODAY)
        contract = component(score, 'contract')
        self.assertEqual(contract.awarded, 0)
        self.assertIn('expired', contract.rationale)
        self.assertIn('Contract has expired', score.flags)

    def test_contract_is_live_on_its_renewal_date(self):
        score = score_vendor(make_vendor(
            security_clauses=True, contract_renewal_date=TODAY,
        ), today=TODAY)
        self.assertEqual(component(score, 'contract').awarded, 12)

    def test_contractual_controls_sum_to_30(self):
        score = score_vendor(make_vendor(
            security_clauses=True, audit_rights=True, sla_defined=True,
            breach_notification_hours=24,
        ), today=TODAY)
        self.assertEqual(component(score, 'contract').awarded, 30)

    def test_breach_window_over_24h_earns_nothing(self):
        score = score_vendor(make_vendor(breach_notification_hours=48), today=TODAY)
        self.assertEqual(component(score, 'contract').awarded, 0)

    def test_assessment_recency_bands(self):
        cases = ((365, 20), (366, 12), (730, 12), (731, 5), (1095, 5), (1096, 0))
        for age, expected in cases:
            with self.subTest(age=age):
                score = score_vendor(make_vendor(
                    last_assessment_date=TODAY - timedelta(days=age),
                ), today=TODAY)
                self.assertEqual(component(score, 'assessment').awarded, expected)

    def test_never_assessed_earns_nothing(self):
        score = score_vendor(make_vendor(last_assessment_date=None), today=TODAY)
        self.assertEqual(component(score, 'assessment').awarded, 0)

    def test_data_access_is_inverted(self):
        for level, expected in ((0, 15), (1, 13), (2, 9), (3, 4), (4, 0)):
            with self.subTest(level=level):
                score = score_vendor(
                    make_vendor(data_sensitivity=level), today=TODAY
                )
                self.assertEqual(component(score, 'data_access').awarded, expected)

    def test_jurisdiction_points(self):
        for jurisdiction, expected in (('eu', 10), ('third', 3), ('unknown', 0)):
            with self.subTest(jurisdiction=jurisdiction):
                score = score_vendor(
                    make_vendor(jurisdiction=jurisdiction, data_sensitivity=0),
                    today=TODAY,
                )
                self.assertEqual(
                    component(score, 'jurisdiction').awarded, expected
                )

    def test_band_boundaries(self):
        cases = ((100, 'low'), (80, 'low'), (79, 'moderate'), (60, 'moderate'),
                 (59, 'elevated'), (40, 'elevated'), (39, 'high'), (0, 'high'))
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(band_for_score(value), expected)

    def test_score_is_the_sum_of_its_components_and_bounded(self):
        combinations = (
            {},
            dict(data_sensitivity=4, jurisdiction='third', tier=1),
            dict(certifications=['ISO27001'], security_clauses=True,
                 audit_rights=True, data_sensitivity=2, jurisdiction='eu'),
            dict(certifications=list(
                ('ISO27001', 'SOC2', 'PCIDSS', 'ISO22301', 'CSA-STAR',
                 'TISAX', 'ISO9001')
            ), security_clauses=True, audit_rights=True, sla_defined=True,
                breach_notification_hours=1, data_sensitivity=0,
                jurisdiction='eu', last_assessment_date=TODAY,
                tier=1),
        )
        for overrides in combinations:
            with self.subTest(overrides=overrides):
                score = score_vendor(make_vendor(**overrides), today=TODAY)
                self.assertEqual(
                    score.score, sum(c.awarded for c in score.components)
                )
                self.assertGreaterEqual(score.score, 0)
                self.assertLessEqual(score.score, 100)

    def test_flags_surface_weaknesses(self):
        score = score_vendor(make_vendor(
            tier=1, audit_rights=False, data_sensitivity=4,
            security_clauses=False, jurisdiction='third',
        ), today=TODAY)
        text = ' | '.join(score.flags)
        self.assertIn('below the 80-point expectation', text)
        self.assertIn('without contractual audit rights', text)
        self.assertIn('sensitive data without contractual security clauses', text)
        self.assertIn('Third-country supplier with data access', text)

    def test_unconfirmed_jurisdiction_is_flagged(self):
        score = score_vendor(make_vendor(jurisdiction='unknown'), today=TODAY)
        self.assertIn('Jurisdiction not confirmed', score.flags)


class VendorScorecardIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Vendor Scoring Dept')
        cls.user = User.objects.create_user(
            'scoring_user', 'scoring@example.com', 'pw', department=cls.dept,
        )
        cls.vendor = Vendor.objects.create(
            name='Acme Cloud', service='cloud', tier=1, status='active',
            owner_dept=cls.dept, contact_name='Acme Contact',
            data_sensitivity=3, jurisdiction='eu',
            certifications=['ISO27001'],
            security_clauses=True, audit_rights=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_scorecard_uses_the_latest_assessment_date(self):
        VendorAssessment.objects.create(
            vendor=self.vendor, assessment_date=TODAY - timedelta(days=400),
            key_findings='Old findings recorded here for the test.',
            recommended_mitigation='Old mitigation recorded here for the test.',
        )
        VendorAssessment.objects.create(
            vendor=self.vendor, assessment_date=TODAY - timedelta(days=20),
            key_findings='New findings recorded here for the test.',
            recommended_mitigation='New mitigation recorded here for the test.',
        )
        self.vendor = Vendor.objects.get(pk=self.vendor.pk)
        self.assertEqual(
            component(self.vendor.scorecard, 'assessment').awarded, 20,
        )

    def test_detail_page_renders_the_scorecard(self):
        response = self.client.get(
            reverse('vendors:detail', kwargs={'pk': self.vendor.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Supplier assurance score')
        self.assertContains(response, 'NIS2 Art. 18')
        self.assertEqual(response.context['scorecard'].score, self.vendor.scorecard.score)

    def test_list_page_shows_an_assurance_column(self):
        response = self.client.get(reverse('vendors:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assurance')

    def test_csv_export_includes_the_assurance_score(self):
        response = self.client.get(
            reverse('vendors:list'), {'export': 'csv'}
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8-sig')
        self.assertIn('Assurance', body)
        self.assertIn(f'{self.vendor.scorecard.score} (', body)

    def test_form_round_trips_certifications_as_a_list(self):
        form = VendorForm(data={
            'name': 'Form Vendor', 'service': 'saas', 'tier': 2,
            'data_sensitivity': 1, 'status': 'active',
            'owner_dept': self.dept.pk, 'contact_name': 'Form Contact',
            'certifications': ['ISO27001', 'SOC2'],
            'jurisdiction': 'eu', 'breach_notification_hours': 12,
        })
        self.assertTrue(form.is_valid(), form.errors)
        vendor = form.save()
        vendor.refresh_from_db()
        self.assertEqual(vendor.certifications, ['ISO27001', 'SOC2'])
        self.assertEqual(vendor.breach_notification_hours, 12)

    def test_form_rejects_unknown_certification(self):
        form = VendorForm(data={
            'name': 'Bad Cert Vendor', 'service': 'saas', 'tier': 2,
            'data_sensitivity': 1, 'status': 'active',
            'owner_dept': self.dept.pk, 'contact_name': 'Form Contact',
            'certifications': ['NOT-A-CERTIFICATION'], 'jurisdiction': 'eu',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('certifications', form.errors)
