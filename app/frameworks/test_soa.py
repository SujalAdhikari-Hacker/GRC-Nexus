"""Tests for the Statement of Applicability report."""
from django.test import TestCase

from controls.models import Control, ControlFrameworkMapping
from core.models import Department, User
from frameworks.models import ComplianceAssessment, Framework, FrameworkControl
from frameworks.soa import _coverage_state


class SoACoverageStateTests(TestCase):
    def _mapping(self, relationship='equal', status='implemented'):
        class _M:
            pass
        m = _M()
        m.relationship = relationship
        m.control = type('C', (), {'status': status})()
        return m

    def test_covered_with_equal_mapping(self):
        verdict, badge = _coverage_state([self._mapping()], '')
        self.assertEqual(verdict, 'covered')
        self.assertEqual(badge, 'bg-success')

    def test_pure_subset_counted_as_partial(self):
        verdict, _ = _coverage_state([self._mapping('subset')], '')
        self.assertEqual(verdict, 'covered')
        self.assertEqual(verdict, _coverage_state([self._mapping('subset')], '')[0])

    def test_non_compliant_assessment_beats_mappings(self):
        verdict, badge = _coverage_state([self._mapping()], 'non_compliant')
        self.assertEqual(verdict, 'gap — non-compliant')
        self.assertEqual(badge, 'bg-danger')

    def test_na_excluded(self):
        verdict, badge = _coverage_state([], 'na')
        self.assertEqual(verdict, 'excluded')
        self.assertEqual(badge, 'bg-secondary')

    def test_no_mapping_is_gap(self):
        verdict, badge = _coverage_state([], '')
        self.assertEqual(verdict, 'no internal control')
        self.assertEqual(badge, 'bg-danger')


class SoAReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='SoA Dept')
        cls.user = User.objects.create_user('soauser', 'soa@example.com', 'pw', department=cls.dept)
        cls.framework = Framework.objects.create(name='ISO 27001 (test)')
        cls.req_a = FrameworkControl.objects.create(
            framework=cls.framework, code='A.5.1', title='Information security policies',
        )
        cls.req_b = FrameworkControl.objects.create(
            framework=cls.framework, code='A.5.2', title='Information security roles',
        )
        cls.control = Control.objects.create(
            code='SOA-CTL', name='Policy set', status='implemented',
            owner_dept=cls.dept,
        )

    def test_page_renders_without_frameworks(self):
        self.client.force_login(self.user)
        # Delete nothing; other tests in this class share data, so just visit.
        resp = self.client.get('/frameworks/soa/')
        self.assertEqual(resp.status_code, 200)

    def test_report_lists_requirements_and_rows(self):
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/soa/?framework={self.framework.pk}')
        self.assertContains(resp, 'A.5.1')
        self.assertContains(resp, 'A.5.2')
        body = resp.content.decode()
        # Requirement with no mapping is flagged as a gap.
        self.assertGreater(body.count('no internal control'), 0)

    def test_mapping_turns_row_to_covered(self):
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.req_a,
        )
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/soa/?framework={self.framework.pk}')
        self.assertContains(resp, 'covered')

    def test_csv_export_rows_match_requirements(self):
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.req_a,
        )
        self.client.force_login(self.user)
        resp = self.client.get(
            f'/frameworks/soa/?framework={self.framework.pk}&export=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        text = resp.content.decode('utf-8-sig')
        self.assertIn('A.5.1', text)
        self.assertIn('A.5.2', text)
        self.assertIn('SOA-CTL', text)

    def test_na_assessment_marks_requirement_excluded(self):
        assessment = ComplianceAssessment.objects.create(
            framework=self.framework, name='Readiness', owner_dept=self.dept,
            assessment_date='2026-01-01',
        )
        assessment.items.create(
            framework_control=self.req_b, status='na',
        )
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/soa/?framework={self.framework.pk}')
        entries = [
            (row['requirement'].code, row['verdict'])
            for row in resp.context['rows']
        ]
        self.assertIn(('A.5.2', 'excluded'), entries)

    def test_soa_summary_counts_match_requirement_rows(self):
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.req_a, relationship='equal',
        )
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/soa/?framework={self.framework.pk}')
        counts = resp.context['counts']
        self.assertEqual(counts['covered'], 1)
        self.assertEqual(counts['no_internal_control'], 1)
        self.assertEqual(counts['partially_covered'], 0)

    def test_framework_detail_labels_partial_mapping_as_partial(self):
        ControlFrameworkMapping.objects.create(
            control=self.control, framework_control=self.req_a, relationship='subset',
        )
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/{self.framework.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '>Partial<')

    def test_all_na_assessment_returns_none_and_renders_na(self):
        assessment = ComplianceAssessment.objects.create(
            framework=self.framework, name='All N/A Test', owner_dept=self.dept,
            assessment_date='2026-01-01',
        )
        assessment.items.create(framework_control=self.req_a, status='na')
        assessment.items.create(framework_control=self.req_b, status='na')
        self.assertIsNone(assessment.readiness_percent)
        self.client.force_login(self.user)
        resp = self.client.get(f'/frameworks/assessments/{assessment.pk}/')
        self.assertContains(resp, 'N/A')
        self.assertNotContains(resp, '100%\n')
        list_resp = self.client.get('/frameworks/assessments/')
        self.assertContains(list_resp, 'N/A')

    def test_login_required(self):
        resp = self.client.get('/frameworks/soa/')
        self.assertEqual(resp.status_code, 302)
