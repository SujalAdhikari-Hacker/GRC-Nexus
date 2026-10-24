"""Tests for sign-in throttling (core.login_throttle)."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core.login_throttle import (
    LOCK_SECONDS,
    MAX_FAILURES,
    clear_failures,
    register_failure,
    seconds_until_unlock,
)


class ThrottleUnitTest(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_lockout_engages_after_max_failures(self):
        for _ in range(MAX_FAILURES - 1):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('alice', '1.2.3.4'))
        register_failure('alice', '1.2.3.4')
        remaining = seconds_until_unlock('alice', '1.2.3.4')
        self.assertTrue(0 < remaining <= LOCK_SECONDS)

    def test_other_usernames_and_ips_unaffected(self):
        for _ in range(MAX_FAILURES):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('bob', '1.2.3.4'))
        self.assertIsNone(seconds_until_unlock('alice', '5.6.7.8'))

    def test_success_clears_counter(self):
        register_failure('alice', '1.2.3.4')
        clear_failures('alice', '1.2.3.4')
        # MAX attempts after a reset do lock — the counter restarted.
        for _ in range(MAX_FAILURES - 1):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('alice', '1.2.3.4'))
        register_failure('alice', '1.2.3.4')
        self.assertIsNotNone(seconds_until_unlock('alice', '1.2.3.4'))


class ThrottleViewTests(TestCase):
    """End-to-end through /login/."""

    @classmethod
    def setUpTestData(cls):
        from core.models import User
        cls.user = User.objects.create_user('bruteforce', 'bf@example.com', 'correct-horse')

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _post(self, password):
        return self.client.post('/login/', {
            'username': 'bruteforce',
            'password': password,
        })

    def test_correct_credentials_still_work_normally(self):
        resp = self._post('correct-horse')
        self.assertEqual(resp.status_code, 302)

    def test_lockout_ignores_correct_password(self):
        with patch('core.login_throttle.MAX_FAILURES', 5):
            for _ in range(5):
                self._post('wrong')
        resp = self._post('correct-horse')
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        self.assertContains(resp, 'Too many failed sign-in attempts')
        # And the session really was not created.
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_lockout_message_renders_generic_alert_after_expiry(self):
        for _ in range(5):
            self._post('wrong')
        # Force the lock to expire: clear the counters only.
        clear_failures('bruteforce', '127.0.0.1')
        resp = self._post('correct-horse')
        self.assertEqual(resp.status_code, 302)

    def test_first_failures_show_generic_message(self):
        resp = self._post('wrong')
        self.assertContains(resp, 'correct username and password')
