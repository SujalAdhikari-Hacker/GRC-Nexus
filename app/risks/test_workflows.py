"""Tests for 1-click Risk detail quick actions (link control & HOD approve/close)."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from controls.models import Control
from core.models import Department, User
from risks.models import Risk, RiskAppetite, RiskCategory


class RiskQuickActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT Sec Workflows')
        cls.staff = User.objects.create_user(
            'rsk_staff', password='StrongPassword!123', department=cls.dept, is_hod=False,
        )
        cls.hod = User.objects.create_user(
            'rsk_hod', password='StrongPassword!123', department=cls.dept, is_hod=True,
        )
        cls.category = RiskCategory.objects.create(name='Cyber')
        RiskAppetite.objects.create(
            department=cls.dept,
            category=cls.category,
            max_inherent_score=15,
            max_residual_score=6,
            risk_capacity=20,
        )
        cls.control = Control.objects.create(
            code='CTL-WF-1',
            name='MFA Enforcement',
            owner_dept=cls.dept,
            control_type='preventive',
            status='implemented',
            lifecycle_status='operational',
            effectiveness_rating='effective',
            last_tested=date.today(),
        )
        cls.risk = Risk.objects.create(
            title='Unprotected Admin Portal',
            category=cls.category,
            owner_dept=cls.dept,
            likelihood=4,
            impact=4,
        )

    def test_link_control_recalculates_residual_score(self):
        before = self.risk.residual_score
        self.assertEqual(before, 16)

        self.client.force_login(self.staff)
        detail_resp = self.client.get(reverse('risks:detail', args=[self.risk.pk]))
        self.assertContains(detail_resp, 'linkControlBox')
        resp = self.client.post(
            reverse('risks:link_control', args=[self.risk.pk]),
            {'control_id': self.control.pk},
        )
        self.assertRedirects(resp, reverse('risks:detail', args=[self.risk.pk]))
        self.risk.refresh_from_db()
        self.assertIn(self.control, self.risk.controls.all())
        self.assertLess(self.risk.residual_score, before)

    def test_approve_close_requires_hod_and_closes_breached_risk(self):
        url = reverse('risks:approve_close', args=[self.risk.pk])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url, {'closure_notes': 'try'}).status_code, 403)

        self.client.force_login(self.hod)
        resp = self.client.post(url, {'closure_notes': 'Compensating controls verified.'})
        self.assertRedirects(resp, reverse('risks:detail', args=[self.risk.pk]))
        self.risk.refresh_from_db()
        self.assertEqual(self.risk.status, 'closed')
        self.assertEqual(self.risk.approved_by, self.hod)
        self.assertIsNotNone(self.risk.closed_date)
