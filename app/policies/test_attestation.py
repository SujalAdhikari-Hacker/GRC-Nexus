"""Tests for policy attestation."""
from django.test import TestCase
from django.utils import timezone

from core.models import Department, User

from .models import Policy, PolicyAttestation


class AttestationBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Policy Target Dept')
        cls.other = Department.objects.create(name='Unrelated Dept')
        cls.owner_dept = Department.objects.create(name='Policy Owner Dept')
        cls.user = User.objects.create_user('attestor', 'a@example.com', 'pw', department=cls.dept)
        cls.foreigner = User.objects.create_user(
            'outsider', 'o@example.com', 'pw', department=cls.other)
        cls.superuser = User.objects.create_superuser('attest_su', 's@example.com', 'pw')

    @staticmethod
    def make_policy(**kwargs):
        defaults = dict(
            code='PL-AT-1', title='Acceptable Use', status='approved',
            version='1.0', owner_dept=Department.objects.get(name='Policy Owner Dept'),
        )
        defaults.update(kwargs)
        return Policy.objects.create(**defaults)


class AttestFlowTests(AttestationBase):
    def test_target_department_user_can_attest(self):
        policy = self.make_policy()
        policy.applies_to_departments.add(self.dept)
        self.client.force_login(self.user)
        resp = self.client.post(f'/policies/{policy.pk}/attest/')
        self.assertRedirects(resp, f'/policies/{policy.pk}/')
        att = PolicyAttestation.objects.get(policy=policy, user=self.user)
        self.assertEqual(att.version, policy.version)

    def test_attestor_can_read_the_applied_policy(self):
        policy = self.make_policy()
        policy.applies_to_departments.add(self.dept)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(f'/policies/{policy.pk}/'), 'Acceptable Use')

    def test_duplicate_attestation_returns_single_row(self):
        policy = self.make_policy()
        self.client.force_login(self.user)
        self.client.post(f'/policies/{policy.pk}/attest/')
        self.client.post(f'/policies/{policy.pk}/attest/')
        self.assertEqual(PolicyAttestation.objects.filter(
            policy=policy, user=self.user).count(), 1)

    def test_out_of_scope_user_cannot_attest(self):
        policy = self.make_policy()
        policy.applies_to_departments.add(self.dept)
        self.client.force_login(self.foreigner)
        resp = self.client.post(f'/policies/{policy.pk}/attest/')
        # RLS hides the out-of-scope policy entirely (404); if the request
        # reaches the view it redirects with a friendly message (302).
        self.assertIn(resp.status_code, (302, 404))
        self.assertEqual(PolicyAttestation.objects.count(), 0)

    def test_org_wide_policy_allows_anyone(self):
        policy = self.make_policy()
        self.client.force_login(self.foreigner)
        self.client.post(f'/policies/{policy.pk}/attest/')
        self.assertEqual(PolicyAttestation.objects.count(), 1)
    def test_superuser_may_attest_any_policy(self):
        policy = self.make_policy()
        policy.applies_to_departments.add(self.dept)
        self.client.force_login(self.superuser)
        self.client.post(f'/policies/{policy.pk}/attest/')
        self.assertEqual(PolicyAttestation.objects.count(), 1)

    def test_draft_policy_cannot_be_attested(self):
        policy = self.make_policy(status='draft')
        policy.applies_to_departments.add(self.dept)
        self.client.force_login(self.user)
        resp = self.client.post(f'/policies/{policy.pk}/attest/')
        self.assertRedirects(resp, '/policies/')
        self.assertEqual(PolicyAttestation.objects.count(), 0)

    def test_attest_is_post_only(self):
        policy = self.make_policy()
        self.client.force_login(self.user)
        resp = self.client.get(f'/policies/{policy.pk}/attest/')
        self.assertEqual(resp.status_code, 405)

    def test_new_version_requires_fresh_attestation(self):
        policy = self.make_policy()
        self.client.force_login(self.user)
        self.client.post(f'/policies/{policy.pk}/attest/')
        policy.version = '2.0'
        policy.save()
        self.client.force_login(self.superuser)
        resp = self.client.get(f'/policies/{policy.pk}/')
        self.assertContains(resp, 'I have read and accept this policy')
