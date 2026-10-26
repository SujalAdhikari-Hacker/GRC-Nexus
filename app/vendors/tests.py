"""Tests for vendor list filtering (regression: tier is an integer column)."""
from django.test import TestCase
from django.urls import reverse

from core.models import Department, User

from .models import Vendor


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
