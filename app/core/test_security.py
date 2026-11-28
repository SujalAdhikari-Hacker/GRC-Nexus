"""Security regression tests for the hardening pass.

These tests are intentionally focused on behaviour a reviewer can observe:
headers, CSRF, rate limits, MFA, upload magic bytes, SSRF, log redaction,
object-level authorization and the dependency baseline.
"""
import logging
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assets.models import Asset, AssetCategory
from core.logging_filters import SensitiveDataFilter, redact
from core.mfa import (
    generate_backup_codes, generate_secret, normalize_backup_code, totp_code,
    verify_totp,
)
from core.models import Department, UserMFA
from core.safe_http import UnsafeURL, safe_get, validate_url
from core.validators import validate_evidence_file
from core.webhooks import (
    WebhookVerificationError, sign_payload, verify_signature,
)

User = get_user_model()


class SecurityHeadersTests(TestCase):
    def test_csp_uses_a_nonce_and_forbids_inline_handlers(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        csp = response['Content-Security-Policy']
        self.assertIn("script-src-attr 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        script_src = re.search(r'script-src ([^;]+)', csp).group(1)
        self.assertNotIn("'unsafe-inline'", script_src)
        self.assertNotIn("'unsafe-eval'", script_src)
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        self.assertContains(response, f'nonce="{nonce}"')
        self.assertNotIn(settings.SECRET_KEY, response.content.decode())

    def test_browser_hardening_headers(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin')
        self.assertEqual(response['Cross-Origin-Resource-Policy'], 'same-origin')
        self.assertEqual(response['X-Permitted-Cross-Domain-Policies'], 'none')
        self.assertIn('camera=()', response['Permissions-Policy'])
        self.assertEqual(response['Referrer-Policy'], 'same-origin')

    def test_no_cors_headers_by_default(self):
        response = self.client.get(reverse('login'))
        self.assertNotIn('Access-Control-Allow-Origin', response)
        self.assertNotIn('Access-Control-Allow-Credentials', response)

    @override_settings(CORS_ALLOWED_ORIGINS=['https://allowed.example'])
    def test_cors_only_for_allowlisted_origin_without_credentials(self):
        response = self.client.get(
            reverse('login'), HTTP_ORIGIN='https://allowed.example'
        )
        self.assertEqual(
            response['Access-Control-Allow-Origin'], 'https://allowed.example'
        )
        self.assertNotIn('Access-Control-Allow-Credentials', response)

        response = self.client.get(
            reverse('login'), HTTP_ORIGIN='https://evil.example'
        )
        self.assertNotIn('Access-Control-Allow-Origin', response)

    def test_no_source_maps_ship(self):
        maps = list((Path(settings.BASE_DIR) / 'static').rglob('*.map'))
        self.assertEqual(maps, [])

    def test_local_storage_is_not_used_for_auth_tokens(self):
        js = ''.join(
            path.read_text(encoding='utf-8')
            for path in (Path(settings.BASE_DIR) / 'static' / 'js').glob('*.js')
        ).lower()
        for marker in ('localstorage.setitem("token', "localstorage.setitem('token",
                       'localstorage.setitem("jwt', "localstorage.setitem('jwt",
                       'access_token', 'refresh_token'):
            self.assertNotIn(marker, js)


class CSRFTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='csrf_user', password='A-very-long-unique-passphrase-42!'
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post(reverse('core:settings'), {'timezone': 'UTC'})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'security token', status_code=403)

    def test_logout_requires_post(self):
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)


class InjectionAndXSSSTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username='security_admin',
            email='security@example.com',
            password='A-very-long-unique-passphrase-42!',
        )
        cls.dept = Department.objects.create(name='Security Test Dept')
        cls.category = AssetCategory.objects.create(name='Security Test Category')

    def setUp(self):
        self.client.force_login(self.user)

    def test_search_payload_does_not_error_or_leak_sql(self):
        response = self.client.get(
            reverse('core:search'), {'q': "' OR 1=1 --"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'OperationalError')
        self.assertNotContains(response, 'Traceback')

    def test_asset_name_is_html_escaped(self):
        payload = '<script>alert("xss")</script>'
        asset = Asset.objects.create(
            name=payload,
            owner_dept=self.dept,
            category=self.category,
        )
        response = self.client.get(
            reverse('assets:detail', args=[asset.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;')
        self.assertNotContains(response, payload)


class ObjectAuthorizationTests(TestCase):
    def setUp(self):
        self.dept_a = Department.objects.create(name='Tenant A')
        self.dept_b = Department.objects.create(name='Tenant B')
        self.category = AssetCategory.objects.create(name='Tenant Category')
        self.user_a = User.objects.create_user(
            username='tenant_a_user',
            password='A-very-long-unique-passphrase-42!',
            department=self.dept_a,
        )
        self.asset_b = Asset.objects.create(
            name='Tenant B secret asset',
            owner_dept=self.dept_b,
            category=self.category,
        )

    def test_cross_department_detail_is_not_found(self):
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse('assets:detail', args=[self.asset_b.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_department_asset_is_not_listed(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('assets:list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.asset_b.name)


class RowLevelSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept_a = Department.objects.create(name='RLS Tenant A')
        cls.dept_b = Department.objects.create(name='RLS Tenant B')
        cls.category = AssetCategory.objects.create(name='RLS Category')
        cls.asset_a = Asset.objects.create(
            name='RLS asset A', owner_dept=cls.dept_a, category=cls.category,
        )
        cls.asset_b = Asset.objects.create(
            name='RLS asset B', owner_dept=cls.dept_b, category=cls.category,
        )

    def test_policies_are_installed_and_forced(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_policies "
                "WHERE policyname = 'grc_dept_isolation'"
            )
            self.assertGreaterEqual(cursor.fetchone()[0], 20)
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = 'assets_asset'"
            )
            self.assertEqual(cursor.fetchone(), (True, True))

    def test_database_rejects_cross_department_rows(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.bypass_rls', 'off', false), "
                    "set_config('app.department_id', %s, false), "
                    "set_config('app.user_id', '', false)",
                    [str(self.dept_a.pk)],
                )
                cursor.execute(
                    'SELECT count(*) FROM assets_asset WHERE id = %s',
                    [self.asset_a.pk],
                )
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    'SELECT count(*) FROM assets_asset WHERE id = %s',
                    [self.asset_b.pk],
                )
                self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.bypass_rls', 'on', false), "
                    "set_config('app.department_id', '', false), "
                    "set_config('app.user_id', '', false)"
                )

    def test_mfa_secrets_are_scoped_to_the_authenticated_user(self):
        user_a = User.objects.create_user(username='rls_mfa_a')
        user_b = User.objects.create_user(username='rls_mfa_b')
        mfa_a = UserMFA.objects.create(user=user_a, secret='A' * 32)
        mfa_b = UserMFA.objects.create(user=user_b, secret='B' * 32)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.bypass_rls', 'off', false), "
                    "set_config('app.department_id', '', false), "
                    "set_config('app.user_id', %s, false)",
                    [str(user_a.pk)],
                )
                cursor.execute(
                    'SELECT id FROM core_usermfa WHERE id IN (%s, %s)',
                    [mfa_a.pk, mfa_b.pk],
                )
                self.assertEqual(cursor.fetchall(), [(mfa_a.pk,)])
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.bypass_rls', 'on', false), "
                    "set_config('app.department_id', '', false), "
                    "set_config('app.user_id', '', false)"
                )


class UploadMagicTests(TestCase):
    def test_pdf_extension_with_html_content_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with self.assertRaises(ValidationError):
            validate_evidence_file(
                SimpleUploadedFile('report.pdf', b'<html>not a pdf</html>')
            )

    def test_office_extension_with_wrong_container_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with self.assertRaises(ValidationError):
            validate_evidence_file(
                SimpleUploadedFile('report.docx', b'%PDF-1.7\n')
            )

    def test_real_pdf_and_png_are_accepted(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        validate_evidence_file(
            SimpleUploadedFile('report.pdf', b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
        )
        validate_evidence_file(
            SimpleUploadedFile('image.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 32)
        )


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @override_settings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_AUTH=2,
        RATE_LIMIT_WINDOW=60,
        RATE_LIMIT_AUTH_BACKOFF_BASE=30,
        RATE_LIMIT_AUTH_BACKOFF_MAX=900,
    )
    def test_login_is_rate_limited_with_backoff(self):
        url = reverse('login')
        first = self.client.post(url, {'username': 'nobody', 'password': 'wrong'})
        second = self.client.post(url, {'username': 'nobody', 'password': 'wrong'})
        third = self.client.post(url, {'username': 'nobody', 'password': 'wrong'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third['Retry-After'], '30')
        self.assertContains(third, 'Too many requests', status_code=429)

    @override_settings(RATE_LIMIT_ENABLED=True, RATE_LIMIT_PUBLIC=1)
    def test_public_requests_are_limited_per_ip(self):
        first = self.client.get('/')
        second = self.client.get('/')
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 429)


class RequestValidationTests(TestCase):
    @override_settings(INPUT_MAX_QUERY_VALUE_LENGTH=10)
    def test_overlong_query_value_is_rejected(self):
        response = self.client.get(reverse('login'), {'next': 'x' * 11})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Bad request', status_code=400)
        self.assertNotContains(response, 'Traceback', status_code=400)

    def test_control_characters_in_query_are_rejected(self):
        response = self.client.get('/login/?next=bad%00value')
        self.assertEqual(response.status_code, 400)

    def test_invalid_query_parameter_name_is_rejected(self):
        response = self.client.get('/login/?bad%20name=value')
        self.assertEqual(response.status_code, 400)

    def test_unsupported_post_content_type_is_rejected(self):
        response = self.client.post(
            reverse('login'),
            data='{"username":"a","password":"b"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_request_id_is_returned_and_sanitised(self):
        response = self.client.get(
            reverse('login'), HTTP_X_REQUEST_ID='trace-123'
        )
        self.assertEqual(response['X-Request-ID'], 'trace-123')

        response = self.client.get(
            reverse('login'), HTTP_X_REQUEST_ID='x' * 200
        )
        self.assertNotEqual(response['X-Request-ID'], 'x' * 200)
        self.assertEqual(len(response['X-Request-ID']), 32)

    def test_error_pages_do_not_leak_internal_details(self):
        response = self.client.get('/definitely-not-a-real-route/')
        self.assertEqual(response.status_code, 404)
        body = response.content.decode()
        for marker in ('Traceback', 'DisallowedHost', 'settings.py', 'django/'):
            self.assertNotIn(marker, body)

        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from config.urls import handler500

        request = RequestFactory().get('/boom')
        request.request_id = 'test-request'
        request.user = AnonymousUser()
        response = handler500(request)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('Traceback', response.content.decode())


class InputHelperTests(TestCase):
    def test_integer_rejects_non_numeric_and_out_of_range(self):
        from core.input_validation import InvalidInput, integer

        for value in ('abc', '1.5', True, '0'):
            with self.subTest(value=value):
                with self.assertRaises(InvalidInput):
                    integer(value, 'n', minimum=1, maximum=5)

    def test_choice_rejects_unknown_values(self):
        from core.input_validation import InvalidInput, choice

        with self.assertRaises(InvalidInput):
            choice('unknown', {'a', 'b'}, 'field')
        self.assertEqual(choice('', {'a', 'b'}, 'field', allow_blank=True), '')

    def test_text_rejects_overlong_values(self):
        from core.input_validation import InvalidInput, text

        with self.assertRaises(InvalidInput):
            text('x' * 11, 'field', 10)

    def test_boolean_rejects_unexpected_values(self):
        from core.input_validation import InvalidInput, boolean

        with self.assertRaises(InvalidInput):
            boolean('maybe', 'flag')


class MFATests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = 'A-very-long-unique-passphrase-42!'
        self.user = User.objects.create_user(
            username='mfa_user', password=self.password,
        )

    def tearDown(self):
        cache.clear()

    def test_enrolment_then_login_requires_a_code(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('core:mfa_setup'))
        self.assertEqual(response.status_code, 200)
        secret = response.context['secret']
        response = self.client.post(
            reverse('core:mfa_setup'), {'code': totp_code(secret)}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'backup')
        mfa = UserMFA.objects.get(user=self.user)
        self.assertTrue(mfa.enabled)
        self.assertTrue(mfa.backup_codes)

        # A fresh session must prove the second factor.
        self.client.logout()
        response = self.client.post(reverse('login'), {
            'username': self.user.username, 'password': self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:mfa_verify'), response['Location'])
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:mfa_verify'), response['Location'])

        response = self.client.post(
            reverse('core:mfa_verify'), {'code': totp_code(secret)}
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_backup_code_is_single_use(self):
        code = 'ABCD-EF12'
        mfa = UserMFA.objects.create(
            user=self.user,
            secret=generate_secret(),
            enabled=True,
            confirmed_at=timezone.now(),
            backup_codes=[make_password(normalize_backup_code(code))],
        )
        self.client.post(reverse('login'), {
            'username': self.user.username, 'password': self.password,
        })
        response = self.client.post(
            reverse('core:mfa_verify'), {'code': code}
        )
        self.assertEqual(response.status_code, 302)
        mfa.refresh_from_db()
        self.assertEqual(mfa.backup_codes, [])

    def test_wrong_code_does_not_complete_login(self):
        secret = generate_secret()
        UserMFA.objects.create(
            user=self.user, secret=secret, enabled=True,
            confirmed_at=timezone.now(),
        )
        self.client.post(reverse('login'), {
            'username': self.user.username, 'password': self.password,
        })
        response = self.client.post(
            reverse('core:mfa_verify'), {'code': '000000'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not valid')
        self.assertFalse(self.client.session.get('mfa_verified', False))

    def test_disable_requires_password_and_code(self):
        secret = generate_secret()
        UserMFA.objects.create(
            user=self.user, secret=secret, enabled=True,
            confirmed_at=timezone.now(),
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('core:mfa_disable'),
            {'password': 'wrong', 'code': totp_code(secret)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserMFA.objects.filter(user=self.user).exists())

        response = self.client.post(
            reverse('core:mfa_disable'),
            {'password': self.password, 'code': totp_code(secret)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserMFA.objects.filter(user=self.user).exists())


class PasswordPolicyTests(TestCase):
    def test_short_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_password('short')

    def test_passwords_are_hashed_with_pbkdf2(self):
        user = User.objects.create_user(
            username='hash_user', password='A-very-long-unique-passphrase-42!'
        )
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
        self.assertNotIn('A-very-long-unique-passphrase-42!', user.password)

    def test_forced_password_rotation_blocks_the_app(self):
        user = User.objects.create_user(
            username='rotate_user',
            password='A-very-long-unique-passphrase-42!',
            must_change_password=True,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('password_change'))

        response = self.client.post(reverse('password_change'), {
            'old_password': 'A-very-long-unique-passphrase-42!',
            'new_password1': 'Another-very-long-unique-passphrase-84!',
            'new_password2': 'Another-very-long-unique-passphrase-84!',
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 200)

    def test_forced_rotation_banner_and_blocks_password_reuse(self):
        user = User.objects.create_user(
            username='reuse_user',
            password='A-very-long-unique-passphrase-42!',
            must_change_password=True,
        )
        self.client.force_login(user)

        get_resp = self.client.get(reverse('password_change'))
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'Password rotation required')
        self.assertNotContains(get_resp, 'Cancel')

        reuse_resp = self.client.post(reverse('password_change'), {
            'old_password': 'A-very-long-unique-passphrase-42!',
            'new_password1': 'A-very-long-unique-passphrase-42!',
            'new_password2': 'A-very-long-unique-passphrase-42!',
        })
        self.assertEqual(reuse_resp.status_code, 200)
        self.assertContains(reuse_resp, 'cannot be the same as your current password')
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)

        ok_resp = self.client.post(reverse('password_change'), {
            'old_password': 'A-very-long-unique-passphrase-42!',
            'new_password1': 'Different-very-long-passphrase-99!',
            'new_password2': 'Different-very-long-passphrase-99!',
        })
        self.assertEqual(ok_resp.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)

    def test_default_password_command_flags_known_accounts(self):
        user = User.objects.create_user(
            username='legacy_demo_user', password='demo1234'
        )
        out = StringIO()
        call_command('flag_default_passwords', '--dry-run', stdout=out)
        self.assertIn('legacy_demo_user', out.getvalue())
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)

        call_command('flag_default_passwords', stdout=StringIO())
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)

    def test_seed_command_has_no_hardcoded_password(self):
        source = (
            Path(settings.BASE_DIR) / 'core' / 'management' / 'commands'
            / 'seed_demo.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn('demo1234', source)


class LoggingRedactionTests(TestCase):
    def test_redact_masks_common_credentials(self):
        text = redact(
            'password=hunter2 token: abc Authorization: Bearer xyz '
            'api_key=key123 csrfmiddlewaretoken=csrf123'
        )
        for secret in ('hunter2', 'abc', 'xyz', 'key123', 'csrf123'):
            self.assertNotIn(secret, text)
        self.assertIn('[REDACTED]', text)

    def test_filter_masks_the_rendered_message(self):
        record = logging.LogRecord(
            'test', logging.INFO, __file__, 1, 'login failed password=secret', (),
            None,
        )
        SensitiveDataFilter().filter(record)
        self.assertNotIn('secret', record.getMessage())


class SSRFAndWebhookTests(TestCase):
    def test_private_and_metadata_addresses_are_rejected(self):
        for url in (
            'http://127.0.0.1/',
            'http://169.254.169.254/latest/meta-data/',
            'http://localhost/',
            'file:///etc/passwd',
            'https://evil.example/',
        ):
            with self.subTest(url=url):
                with self.assertRaises(UnsafeURL):
                    validate_url(url)

    def test_safe_get_rejects_loopback_before_network(self):
        with self.assertRaises(UnsafeURL):
            safe_get('http://127.0.0.1:8000/')

    def test_http_is_rejected_even_for_allowlisted_hosts(self):
        with self.assertRaises(UnsafeURL):
            validate_url('http://services.nvd.nist.gov/')

    def test_credentials_and_invalid_ports_are_rejected(self):
        for url in (
            'https://user:pass@services.nvd.nist.gov/',
            'https://services.nvd.nist.gov:99999/',
        ):
            with self.subTest(url=url):
                with self.assertRaises(UnsafeURL):
                    validate_url(url)

    def test_ipv4_mapped_ipv6_is_checked_as_ipv4(self):
        for address in (
            '::ffff:127.0.0.1', '::ffff:10.0.0.1', '::ffff:169.254.169.254',
        ):
            with self.subTest(address=address):
                with self.assertRaises(UnsafeURL):
                    validate_url(
                        f'https://[{address}]/', allowed_hosts={address},
                    )

    def test_non_global_ranges_are_rejected(self):
        for address in (
            '100.64.0.1', '192.0.2.1', '198.18.0.1', '2001:db8::1',
        ):
            with self.subTest(address=address):
                host = f'[{address}]' if ':' in address else address
                with self.assertRaises(UnsafeURL):
                    validate_url(f'https://{host}/', allowed_hosts={address})

    def test_dns_resolving_to_a_private_address_is_rejected(self):
        from unittest.mock import patch

        infos = [(2, 1, 6, '', ('10.0.0.5', 0))]
        with patch('core.safe_http.socket.getaddrinfo', return_value=infos):
            with self.assertRaises(UnsafeURL):
                validate_url('https://services.nvd.nist.gov/')

    def test_a_public_allowlisted_host_passes(self):
        from unittest.mock import patch

        infos = [(2, 1, 6, '', ('93.184.216.34', 0))]
        with patch('core.safe_http.socket.getaddrinfo', return_value=infos):
            self.assertEqual(
                validate_url('https://services.nvd.nist.gov/'),
                'https://services.nvd.nist.gov/',
            )

    def test_webhook_signature_round_trip(self):
        payload = b'{"event":"risk.created"}'
        header = f't=1000,v1={sign_payload("topsecret", 1000, payload)}'
        self.assertTrue(
            verify_signature(payload, header, 'topsecret', now=1000)
        )

    def test_webhook_rejects_tampering_and_replay(self):
        payload = b'{"event":"risk.created"}'
        header = f't=1000,v1={sign_payload("topsecret", 1000, payload)}'
        with self.assertRaises(WebhookVerificationError):
            verify_signature(payload + b'x', header, 'topsecret', now=1000)
        with self.assertRaises(WebhookVerificationError):
            verify_signature(payload, header, 'topsecret', now=2000)
        with self.assertRaises(WebhookVerificationError):
            verify_signature(payload, 'nonsense', 'topsecret', now=1000)


class DependencyBaselineTests(TestCase):
    def test_django_is_a_supported_lts(self):
        import django
        self.assertGreaterEqual(django.VERSION[:2], (5, 2))


class ClientIPTests(SimpleTestCase):
    """Rate limits must key on the real client only behind trusted proxies."""

    def _request(self, remote='10.0.0.9', forwarded=None):
        from django.test import RequestFactory
        extra = {'REMOTE_ADDR': remote}
        if forwarded is not None:
            extra['HTTP_X_FORWARDED_FOR'] = forwarded
        return RequestFactory().get('/', **extra)

    def test_remote_addr_is_used_by_default(self):
        from core.rate_limit import client_ip
        request = self._request(forwarded='203.0.113.7')
        self.assertEqual(client_ip(request), '10.0.0.9')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_single_proxy_uses_forwarded_address(self):
        from core.rate_limit import client_ip
        request = self._request(forwarded='203.0.113.7')
        self.assertEqual(client_ip(request), '203.0.113.7')

    @override_settings(TRUSTED_PROXY_HOPS=2)
    def test_two_proxies_skip_the_inner_hop(self):
        from core.rate_limit import client_ip
        request = self._request(forwarded='203.0.113.7, 10.0.0.2')
        self.assertEqual(client_ip(request), '203.0.113.7')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_spoofed_or_malformed_headers_fall_back(self):
        from core.rate_limit import client_ip
        for header in ('not-an-ip', 'unknown, bogus', ''):
            with self.subTest(header=header):
                request = self._request(forwarded=header)
                self.assertEqual(client_ip(request), '10.0.0.9')

    @override_settings(TRUSTED_PROXY_HOPS=1)
    def test_ipv6_and_port_forms_are_normalised(self):
        from core.rate_limit import client_ip
        self.assertEqual(
            client_ip(self._request(forwarded='2001:db8::1')),
            '2001:db8::1',
        )
        self.assertEqual(
            client_ip(self._request(forwarded='203.0.113.7:443')),
            '203.0.113.7',
        )


class DeploySettingsTests(SimpleTestCase):
    """The documented TLS profile must satisfy Django's deployment checks."""

    TLS_IDS = {'security.W004', 'security.W008', 'security.W012', 'security.W016'}

    def _deploy_warnings(self):
        from django.core.checks import run_checks
        return run_checks(tags=['security'], include_deployment_checks=True)

    def test_tls_profile_clears_the_transport_warnings(self):
        with override_settings(
            DEBUG=False,
            SECURE_SSL_REDIRECT=True,
            SECURE_HSTS_SECONDS=31_536_000,
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
        ):
            ids = {message.id for message in self._deploy_warnings()}
        self.assertFalse(self.TLS_IDS & ids, self.TLS_IDS & ids)

    def test_local_http_profile_reports_them(self):
        with override_settings(
            DEBUG=False,
            SECURE_SSL_REDIRECT=False,
            SECURE_HSTS_SECONDS=0,
            SESSION_COOKIE_SECURE=False,
            CSRF_COOKIE_SECURE=False,
        ):
            ids = {message.id for message in self._deploy_warnings()}
        self.assertTrue(self.TLS_IDS <= ids, self.TLS_IDS - ids)


class ErrorPageContextTests(SimpleTestCase):
    """A 400/500 can render before AuthenticationMiddleware sets request.user."""

    def test_context_processors_tolerate_missing_user(self):
        from django.test import RequestFactory

        from core.context_processors import (
            notification_count,
            pending_actions,
            recent_notifications_context,
            user_preference_context,
        )
        from incidents.context_processors import incident_counters
        from tickets.context_processors import ticket_counters

        request = RequestFactory().get('/')
        self.assertFalse(hasattr(request, 'user'))

        self.assertEqual(pending_actions(request), {})
        self.assertEqual(ticket_counters(request), {})
        self.assertEqual(incident_counters(request), {})
        self.assertEqual(
            notification_count(request),
            {'unread_notification_count': 0},
        )
        self.assertEqual(
            recent_notifications_context(request),
            {'recent_notifications': [], 'unread_notification_count': 0},
        )
        self.assertEqual(
            user_preference_context(request)['user_theme_pref'], 'system'
        )


class AdminSuperuserOnlyTests(TestCase):
    """Django Admin is strictly reserved for active superusers (never department HODs)."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Admin Lock Dept')
        cls.hod_staff = User.objects.create_user(
            'hod_with_staff', 'hws@example.com', 'pw',
            department=cls.dept, is_hod=True, is_staff=True,
        )
        cls.superuser = User.objects.create_superuser(
            'real_superadmin', 'rsa@example.com', 'pw',
        )

    def test_non_superuser_staff_is_blocked_from_django_admin_and_links(self):
        from tickets.models import Ticket

        ticket = Ticket.objects.create(title='Admin link test', owner_dept=self.dept)
        self.client.force_login(self.hod_staff)

        for admin_path in ('/admin/', '/admin/core/user/'):
            with self.subTest(path=admin_path):
                resp = self.client.get(admin_path)
                self.assertEqual(resp.status_code, 302)
                self.assertIn('/admin/login/', resp['Location'])

        detail_resp = self.client.get(reverse('tickets:detail', kwargs={'pk': ticket.pk}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertNotContains(detail_resp, reverse('admin:tickets_ticket_change', args=[ticket.pk]))

    def test_superuser_can_open_django_admin(self):
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
