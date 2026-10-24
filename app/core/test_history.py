"""Tests for the merged change-log page (core.history_views)."""
from django.test import TestCase

from assets.models import Asset
from core.models import Department, User


class ChangeLogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='CL Dept')
        cls.other = Department.objects.create(name='CL Other')
        cls.plain = User.objects.create_user('clplain', 'clp@example.com', 'pw', department=cls.dept)
        cls.hod = User.objects.create_user('clhod', 'clh@example.com', 'pw', department=cls.dept, is_hod=True)
        cls.superuser = User.objects.create_superuser('clsu', 'cls@example.com', 'pw')

    def test_page_exists_for_hod_and_superuser(self):
        for user in (self.hod, self.superuser):
            self.client.force_login(user)
            resp = self.client.get('/history/')
            self.assertEqual(resp.status_code, 200, user)

    def test_page_denied_for_plain_users(self):
        self.client.force_login(self.plain)
        resp = self.client.get('/history/')
        self.assertEqual(resp.status_code, 403)

    def test_requires_login(self):
        resp = self.client.get('/history/')
        self.assertEqual(resp.status_code, 302)

    def test_recent_change_shows_up(self):
        self.client.force_login(self.superuser)
        Asset.objects.create(name='Changed asset', owner_dept=self.dept)
        resp = self.client.get('/history/')
        entries = resp.context['entries']
        self.assertTrue(any(e['repr'].endswith('Changed asset') and e['type'] == '+'
                            for e in entries))

    def test_filter_by_register_and_type(self):
        self.client.force_login(self.superuser)
        asset = Asset.objects.create(name='Filtered asset', owner_dept=self.dept)
        resp = self.client.get('/history/', {'model': 'assets.asset', 'type': '+'})
        entries = resp.context['entries']
        self.assertTrue(entries)
        self.assertTrue(all(e['type'] == '+' for e in entries))
        self.assertTrue(any(e['repr'].endswith('Filtered asset') for e in entries))
        # Filtering for deletions must show nothing for this asset.
        resp = self.client.get('/history/', {'model': 'assets.asset', 'type': '-'})
        self.assertFalse(resp.context['entries'])

    def test_search_narrows_results(self):
        Asset.objects.create(name='Zebra-searchable', owner_dept=self.dept)
        self.client.force_login(self.superuser)
        resp = self.client.get('/history/', {'q': 'Zebra'})
        self.assertTrue(any('Zebra-searchable' in e['repr']
                            for e in resp.context['entries']))
        resp = self.client.get('/history/', {'q': 'no-such-record-name-123'})
        self.assertFalse(resp.context['entries'])
        self.assertContains(resp, 'No changes match')
