"""Tests for audit list filters (regression: priority is an integer column)."""
from django.test import TestCase
from django.urls import reverse

from core.models import Department, User

from .models import ActionItem, AuditFinding


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
