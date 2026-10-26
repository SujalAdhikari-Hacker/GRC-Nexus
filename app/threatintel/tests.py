"""Tests for the IOC feed filters (regression: confidence is an integer column)."""
from django.test import TestCase
from django.urls import reverse

from core.models import User

from .models import IOC


class IOCFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'ioc_user', 'ioc@example.com', 'pw',
        )
        cls.high = IOC.objects.create(
            value='203.0.113.10', ioc_type='ipv4', threat_type='c2',
            confidence=3, source='test',
        )
        cls.low = IOC.objects.create(
            value='198.51.100.20', ioc_type='domain', threat_type='phishing',
            confidence=1, source='test',
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _values(self, response):
        return {ioc.value for ioc in response.context['iocs']}

    def test_confidence_filter_accepts_integer_values(self):
        response = self.client.get(
            reverse('threatintel:ioc_feed'), {'confidence': '3'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._values(response), {'203.0.113.10'})

    def test_other_filters_still_work(self):
        response = self.client.get(
            reverse('threatintel:ioc_feed'),
            {'type': 'domain', 'threat': 'phishing', 'confidence': '1'},
        )
        self.assertEqual(self._values(response), {'198.51.100.20'})

    def test_invalid_filters_are_rejected(self):
        for params in (
            {'confidence': '5'},
            {'confidence': 'high'},
            {'type': 'not-a-type'},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    reverse('threatintel:ioc_feed'), params,
                )
                self.assertEqual(response.status_code, 400)
