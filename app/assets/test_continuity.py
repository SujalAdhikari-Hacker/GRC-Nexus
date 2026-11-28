"""BIA / continuity gap checks on assets."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Department, User
from policies.models import Policy

from .models import Asset


class ContinuityGapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Continuity Dept')
        cls.other_dept = Department.objects.create(name='Other Dept')
        cls.user = User.objects.create_user(
            'continuity', 'continuity@example.com', 'pw', department=cls.dept,
        )
        cls.bcp = Policy.objects.create(
            title='Business Continuity Plan', code='BCP-001',
            owner_dept=cls.dept,
        )
        cls.drp = Policy.objects.create(
            title='Disaster Recovery Plan', code='DRP-001',
            owner_dept=cls.dept,
        )

    def _asset(self, **kw):
        defaults = dict(
            name='Payments service', owner_dept=self.dept, criticality=3,
        )
        defaults.update(kw)
        return Asset.objects.create(**defaults)

    def test_an_asset_with_no_bia_has_every_gap(self):
        gaps = self._asset().continuity_gaps
        self.assertIn('RTO not set', gaps)
        self.assertIn('RPO not set', gaps)
        self.assertIn('MTPD not set', gaps)
        self.assertIn('No BCP linked', gaps)
        self.assertIn('No DRP linked', gaps)
        self.assertIn('No continuity test in the last 12 months', gaps)

    def test_a_complete_bia_has_no_gaps(self):
        asset = self._asset(
            rto_hours=4, rpo_hours=1, mtpd_hours=24,
            bcp_policy=self.bcp, drp_policy=self.drp,
            last_continuity_test=timezone.localdate(),
        )
        self.assertEqual(asset.continuity_gaps, [])
        self.assertTrue(asset.continuity_complete)

    def test_rto_longer_than_mtpd_is_a_gap(self):
        asset = self._asset(
            rto_hours=48, rpo_hours=1, mtpd_hours=24,
            bcp_policy=self.bcp, drp_policy=self.drp,
            last_continuity_test=timezone.localdate(),
        )
        self.assertIn('RTO exceeds MTPD', asset.continuity_gaps)

    def test_a_test_older_than_a_year_is_stale(self):
        asset = self._asset(
            rto_hours=4, rpo_hours=1, mtpd_hours=24,
            bcp_policy=self.bcp, drp_policy=self.drp,
            last_continuity_test=timezone.localdate() - timedelta(days=366),
        )
        self.assertTrue(asset.continuity_test_stale)
        self.assertIn('No continuity test in the last 12 months', asset.continuity_gaps)

    def test_the_report_lists_only_gapped_critical_assets_in_the_users_department(self):
        broken = self._asset(name='Broken service', criticality=4)
        healthy = self._asset(
            name='Healthy service', criticality=4,
            rto_hours=4, rpo_hours=1, mtpd_hours=24,
            bcp_policy=self.bcp, drp_policy=self.drp,
            last_continuity_test=timezone.localdate(),
        )
        low = self._asset(name='Low priority', criticality=1)
        other = Asset.objects.create(
            name='Other dept service', owner_dept=self.other_dept, criticality=4,
        )

        self.client.force_login(self.user)
        resp = self.client.get('/assets/continuity-gaps/')

        self.assertEqual(resp.status_code, 200)
        reported = [row['asset'] for row in resp.context['rows']]
        self.assertIn(broken, reported)
        self.assertNotIn(healthy, reported)
        self.assertNotIn(low, reported)
        self.assertNotIn(other, reported)
        self.assertEqual(resp.context['scoped_total'], 2)

    def test_the_detail_page_shows_the_bia(self):
        asset = self._asset(
            rto_hours=4, rpo_hours=1, mtpd_hours=24,
            bcp_policy=self.bcp, drp_policy=self.drp,
            last_continuity_test=timezone.localdate(),
        )
        self.client.force_login(self.user)
        resp = self.client.get(f'/assets/{asset.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Business continuity (BIA)')
        self.assertContains(resp, '4 hours')
        self.assertContains(resp, 'BCP-001')

    def test_the_edit_form_includes_the_bia_fields(self):
        asset = self._asset()
        self.client.force_login(self.user)
        resp = self.client.get(f'/assets/{asset.pk}/edit/')
        self.assertEqual(resp.status_code, 200)
        for field in (
            'rto_hours', 'rpo_hours', 'mtpd_hours',
            'bcp_policy', 'drp_policy', 'last_continuity_test',
        ):
            self.assertContains(resp, f'name="{field}"')
