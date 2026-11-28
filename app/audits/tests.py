"""Tests for audit list filters (regression: priority is an integer column)."""
from django.test import TestCase
from django.urls import reverse

from core.models import Department, User

from .models import ActionItem, Audit, AuditFinding, ControlTest


class ActionItemFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Audit Dept')
        cls.user = User.objects.create_user(
            'audit_user', 'audit@example.com', 'pw', department=cls.dept,
        )
        cls.finding = AuditFinding.objects.create(
            title='Missing MFA', owner_dept=cls.dept, severity='high',
        )
        cls.critical = ActionItem.objects.create(
            finding=cls.finding, title='Enforce MFA', owner_dept=cls.dept,
            priority=4, status='in_progress',
        )
        cls.low = ActionItem.objects.create(
            finding=cls.finding, title='Update policy', owner_dept=cls.dept,
            priority=1, status='not_started',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _titles(self, response):
        return {item.title for item in response.context['actions']}

    def test_priority_filter_accepts_integer_values(self):
        response = self.client.get(
            reverse('audits:action_list'), {'priority': '4'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._titles(response), {'Enforce MFA'})

    def test_status_filter_still_works(self):
        response = self.client.get(
            reverse('audits:action_list'), {'status': 'not_started'},
        )
        self.assertEqual(self._titles(response), {'Update policy'})

    def test_invalid_filters_are_rejected(self):
        for params in ({'priority': '5'}, {'priority': 'critical'}):
            with self.subTest(params=params):
                response = self.client.get(
                    reverse('audits:action_list'), params,
                )
                self.assertEqual(response.status_code, 400)


class AuditConsistencyTests(TestCase):
    """ControlTest result choices are clean and open finding counts match across views."""

    def test_control_test_result_choices_only_valid_outcomes(self):
        self.assertEqual(
            ControlTest.RESULT_CHOICES,
            [('pass', 'Pass'), ('partial', 'Partial'), ('fail', 'Fail')],
        )
        dept = Department.objects.create(name='Test Choice Dept')
        user = User.objects.create_user(
            'test_choice_user', 'tc@example.com', 'pw', department=dept,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('audits:test_list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('Continuous Complaint', html)
        self.assertNotIn('continuous_complaint', html)

    def test_finding_list_open_count_matches_audit_list_open_count(self):
        dept = Department.objects.create(name='Finding Count Dept')
        user = User.objects.create_user(
            'finding_count_user', 'fc@example.com', 'pw', department=dept,
        )
        audit = Audit.objects.create(name='Q1 Security Audit', owner_dept=dept)
        AuditFinding.objects.create(title='Open F', audit=audit, owner_dept=dept, status='open')
        AuditFinding.objects.create(title='WIP F', audit=audit, owner_dept=dept, status='in_progress')
        AuditFinding.objects.create(title='Verified F', audit=audit, owner_dept=dept, status='verified')
        AuditFinding.objects.create(title='Resolved F', audit=audit, owner_dept=dept, status='resolved')
        AuditFinding.objects.create(
            title='Closed F', audit=audit, owner_dept=dept,
            status='closed', verification_status='verified',
        )
        AuditFinding.objects.create(title='Accepted F', audit=audit, owner_dept=dept, status='accepted')

        self.client.force_login(user)
        finding_resp = self.client.get(reverse('audits:finding_list'))
        audit_resp = self.client.get(reverse('audits:list'))
        self.assertEqual(finding_resp.status_code, 200)
        self.assertEqual(audit_resp.status_code, 200)
        self.assertEqual(finding_resp.context['open_count'], 3)
        self.assertEqual(audit_resp.context['open_findings_count'], finding_resp.context['open_count'])
