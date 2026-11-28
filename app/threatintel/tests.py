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


class AttackSyncAndEmptyStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'ti_viewer', 'tiviewer@example.com', 'StrongPassword!123',
        )
        cls.superuser = User.objects.create_superuser(
            'ti_admin', 'tiadmin@example.com', 'StrongPassword!123',
        )

    def test_empty_states_render_sync_guidance(self):
        self.client.force_login(self.superuser)
        r_matrix = self.client.get(reverse('threatintel:attack_matrix'))
        self.assertContains(r_matrix, 'Sync ATT&amp;CK Matrix')
        r_actors = self.client.get(reverse('threatintel:actor_list'))
        self.assertContains(r_actors, 'Sync ATT&amp;CK &amp; Threat Actors')

    def test_seed_baseline_populates_tactics_techniques_actors_and_service_run(self):
        from io import StringIO
        from django.core.management import call_command
        from core.models import ServiceRun
        from .models import Tactic, Technique, ThreatActor

        call_command('sync_attack_data', seed_baseline=True, stdout=StringIO())
        self.assertGreaterEqual(Tactic.objects.count(), 14)
        self.assertGreaterEqual(Technique.objects.count(), 25)
        self.assertGreaterEqual(ThreatActor.objects.count(), 10)

        run = ServiceRun.objects.get(service='sync_attack_data')
        self.assertEqual(run.status, 'ok')
        self.assertGreaterEqual(run.counts.get('actors', 0), 10)

    def test_sync_attack_view_requires_superuser(self):
        url = reverse('threatintel:sync_attack')
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(self.superuser)
        from unittest.mock import patch
        with patch('threatintel.management.commands.sync_attack_data.safe_get', side_effect=RuntimeError('offline')):
            resp = self.client.post(url)
        self.assertRedirects(resp, reverse('threatintel:attack_matrix'))
        from .models import ThreatActor
        self.assertGreaterEqual(ThreatActor.objects.count(), 10)
        r_mat = self.client.get(reverse('threatintel:attack_matrix'))
        self.assertEqual(r_mat.context['total_techniques'], 30)
