"""Tests for sign-in throttling (core.login_throttle)."""
from django.core.cache import cache
from django.test import TestCase, override_settings

from core.login_throttle import (
    clear_failures,
    clear_ip_failures,
    register_failure,
    seconds_until_unlock,
)


@override_settings(
    LOGIN_MAX_FAILURES=5,
    LOGIN_FAILURE_WINDOW=900,
    LOGIN_BACKOFF_BASE_SECONDS=30,
    LOGIN_BACKOFF_MAX_SECONDS=900,
    LOGIN_BACKOFF_MULTIPLIER=2,
    LOGIN_IP_MAX_FAILURES=20,
    LOGIN_IP_BACKOFF_BASE_SECONDS=60,
    LOGIN_IP_BACKOFF_MAX_SECONDS=3600,
)
class ThrottleUnitTest(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_backoff_engages_after_max_failures(self):
        for _ in range(4):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('alice', '1.2.3.4'))
        register_failure('alice', '1.2.3.4')
        remaining = seconds_until_unlock('alice', '1.2.3.4')
        self.assertIsNotNone(remaining)
        self.assertTrue(0 < remaining <= 30)

    def test_backoff_grows_exponentially(self):
        for _ in range(5):
            register_failure('alice', '1.2.3.4')
        first = seconds_until_unlock('alice', '1.2.3.4')
        register_failure('alice', '1.2.3.4')
        second = seconds_until_unlock('alice', '1.2.3.4')
        register_failure('alice', '1.2.3.4')
        third = seconds_until_unlock('alice', '1.2.3.4')
        self.assertGreater(second, first)
        self.assertGreater(third, second)
        self.assertLessEqual(third, 900)

    def test_backoff_is_capped(self):
        for _ in range(20):
            register_failure('alice', '1.2.3.4')
        self.assertLessEqual(seconds_until_unlock('alice', '1.2.3.4'), 900)

    def test_other_usernames_and_ips_unaffected(self):
        for _ in range(5):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('bob', '1.2.3.4'))
        self.assertIsNone(seconds_until_unlock('bob', '5.6.7.8'))
        # The account counter follows the username, not the address.
        self.assertIsNotNone(seconds_until_unlock('alice', '5.6.7.8'))

    def test_success_clears_only_the_account_counter(self):
        for _ in range(5):
            register_failure('alice', '1.2.3.4')
        clear_failures('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('alice', '1.2.3.4'))

        # Four more failures do not lock the account again: the counter reset.
        for _ in range(4):
            register_failure('alice', '1.2.3.4')
        self.assertIsNone(seconds_until_unlock('alice', '1.2.3.4'))
        register_failure('alice', '1.2.3.4')
        self.assertIsNotNone(seconds_until_unlock('alice', '1.2.3.4'))

    @override_settings(LOGIN_IP_MAX_FAILURES=3, LOGIN_IP_BACKOFF_BASE_SECONDS=10)
    def test_ip_counter_is_not_cleared_by_a_successful_account(self):
        for username in ('alice', 'bob', 'carol'):
            register_failure(username, '1.2.3.4')
        self.assertIsNotNone(seconds_until_unlock('dave', '1.2.3.4'))

        clear_failures('dave', '1.2.3.4')
        self.assertIsNotNone(seconds_until_unlock('dave', '1.2.3.4'))

        clear_ip_failures('1.2.3.4')
        self.assertIsNone(seconds_until_unlock('dave', '1.2.3.4'))


@override_settings(
    LOGIN_MAX_FAILURES=5,
    LOGIN_FAILURE_WINDOW=900,
    LOGIN_BACKOFF_BASE_SECONDS=30,
    LOGIN_BACKOFF_MAX_SECONDS=900,
    LOGIN_BACKOFF_MULTIPLIER=2,
    LOGIN_IP_MAX_FAILURES=20,
)
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

    def test_backoff_ignores_correct_password(self):
        for _ in range(5):
            self._post('wrong')
        resp = self._post('correct-horse')
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        self.assertContains(resp, 'Too many failed sign-in attempts')
        # And the session really was not created.
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_backoff_expires(self):
        for _ in range(5):
            self._post('wrong')
        # Force the cool-down to expire without granting a free pass.
        clear_failures('bruteforce', '127.0.0.1')
        clear_ip_failures('127.0.0.1')
        resp = self._post('correct-horse')
        self.assertEqual(resp.status_code, 302)

    def test_first_failures_show_generic_message(self):
        resp = self._post('wrong')
        self.assertContains(resp, 'correct username and password')
