"""Tests for database-backed SMTP settings and notification email delivery.

Run with:
    python manage.py test core.test_email_settings
"""
from unittest import mock

from django.core import mail
from django.core.mail import get_connection
from django.test import TestCase, override_settings
from django.urls import reverse

from core.crypto import decrypt_secret, encrypt_secret
from core.email_config import (
    IMMEDIATE_KINDS,
    build_connection,
    describe,
    from_header,
    send_notification_email,
    send_test_message,
)
from core.models import Department, User
from core.notifications import Notification, create_notification
from core.settings_forms import EmailSettingsForm
from core.settings_model import EmailSettings, UserPreference


def locmem_connection(*args, **kwargs):
    return get_connection('django.core.mail.backends.locmem.EmailBackend')


class CryptoTests(TestCase):
    def test_round_trip(self):
        token = encrypt_secret('hunter2')
        self.assertNotIn('hunter2', token)
        self.assertEqual(decrypt_secret(token), 'hunter2')

    def test_empty_values_stay_empty(self):
        self.assertEqual(encrypt_secret(''), '')
        self.assertEqual(decrypt_secret(''), '')

    def test_corrupt_token_returns_empty_string(self):
        self.assertEqual(decrypt_secret('not-a-fernet-token'), '')


class EmailSettingsModelTests(TestCase):
    def setUp(self):
        EmailSettings.objects.all().delete()

    def test_get_solo_creates_and_reuses_one_row(self):
        first = EmailSettings.get_solo()
        second = EmailSettings.get_solo()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(EmailSettings.objects.count(), 1)

    def test_save_forces_singleton_pk(self):
        EmailSettings(pk=99, host='example.test').save()
        self.assertEqual(EmailSettings.objects.count(), 1)
        self.assertEqual(EmailSettings.get_solo().host, 'example.test')

    def test_password_is_encrypted_and_decrypted(self):
        cfg = EmailSettings.get_solo()
        cfg.set_password('s3cret')
        cfg.save()
        cfg.refresh_from_db()
        self.assertNotIn('s3cret', cfg.password_encrypted)
        self.assertEqual(cfg.password, 's3cret')

    def test_from_header(self):
        cfg = EmailSettings.get_solo()
        cfg.from_name = 'GRC Nexus'
        cfg.from_email = 'no-reply@everest.local'
        self.assertEqual(cfg.from_header, 'GRC Nexus <no-reply@everest.local>')
        cfg.from_name = ''
        self.assertEqual(cfg.from_header, 'no-reply@everest.local')

    def test_security_helpers(self):
        cfg = EmailSettings.get_solo()
        cfg.security = 'starttls'
        self.assertTrue(cfg.use_tls)
        self.assertFalse(cfg.use_ssl)
        cfg.security = 'ssl'
        self.assertFalse(cfg.use_tls)
        self.assertTrue(cfg.use_ssl)


class EmailSettingsFormTests(TestCase):
    def setUp(self):
        EmailSettings.objects.all().delete()

    def _data(self, **overrides):
        data = {
            'is_enabled': 'on',
            'host': '192.168.56.10',
            'port': '25',
            'security': 'none',
            'username': '',
            'from_name': 'GRC Nexus',
            'from_email': 'no-reply@everest.local',
            'timeout': '20',
            'notify_on_new': 'on',
        }
        data.update(overrides)
        return data

    def test_valid_configuration(self):
        form = EmailSettingsForm(self._data(), instance=EmailSettings.get_solo())
        self.assertTrue(form.is_valid(), form.errors)

    def test_enabled_requires_host(self):
        form = EmailSettingsForm(
            self._data(host=''), instance=EmailSettings.get_solo(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('host', form.errors)

    def test_enabled_requires_from_address(self):
        form = EmailSettingsForm(
            self._data(from_email=''), instance=EmailSettings.get_solo(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('from_email', form.errors)

    def test_ssl_on_587_is_rejected(self):
        form = EmailSettingsForm(
            self._data(security='ssl', port='587'),
            instance=EmailSettings.get_solo(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('port', form.errors)

    def test_port_range_is_enforced(self):
        form = EmailSettingsForm(
            self._data(port='70000'), instance=EmailSettings.get_solo(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('port', form.errors)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='GRC Nexus <default@example.test>',
)
class BackendSelectionTests(TestCase):
    def setUp(self):
        EmailSettings.objects.all().delete()
        self.cfg = EmailSettings.get_solo()
        self.cfg.host = '192.168.56.10'
        self.cfg.port = 25
        self.cfg.security = 'none'
        self.cfg.from_name = 'GRC Nexus'
        self.cfg.from_email = 'no-reply@everest.local'
        self.cfg.save()

    def test_disabled_uses_default_backend(self):
        self.cfg.is_enabled = False
        self.cfg.save()
        connection = build_connection()
        self.assertEqual(
            connection.__class__.__module__,
            'django.core.mail.backends.locmem',
        )
        self.assertEqual(from_header(), 'GRC Nexus <default@example.test>')
        self.assertIn('locmem', describe())

    def test_enabled_uses_smtp_backend(self):
        self.cfg.is_enabled = True
        self.cfg.save()
        connection = build_connection()
        self.assertEqual(
            connection.__class__.__module__,
            'django.core.mail.backends.smtp',
        )
        self.assertEqual(connection.host, '192.168.56.10')
        self.assertEqual(connection.port, 25)
        self.assertEqual(
            from_header(), 'GRC Nexus <no-reply@everest.local>',
        )
        self.assertIn('192.168.56.10:25', describe())

    def test_test_message_is_sent_with_configured_from(self):
        self.cfg.is_enabled = True
        self.cfg.save()
        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_test_message('someone@everest.local')
        self.assertEqual(delivered, 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['someone@everest.local'])
        self.assertEqual(
            message.from_email, 'GRC Nexus <no-reply@everest.local>',
        )
        self.assertIn('SMTP test message', message.subject)


class EmailSettingsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Email Dept')
        cls.plain = User.objects.create_user(
            'email_plain', 'plain@everest.local', 'pw', department=cls.dept,
        )
        cls.superuser = User.objects.create_superuser(
            'email_admin', 'admin@everest.local', 'pw',
        )

    def setUp(self):
        EmailSettings.objects.all().delete()

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse('core:email_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_non_superuser_is_forbidden(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse('core:email_settings'))
        self.assertEqual(response.status_code, 403)

    def test_superuser_sees_the_form(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('core:email_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SMTP server')
        self.assertContains(response, 'Send a test message')

    def test_post_saves_and_encrypts_password(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse('core:email_settings'), {
            'is_enabled': 'on',
            'host': '192.168.56.10',
            'port': '25',
            'security': 'none',
            'username': '',
            'password': 's3cret',
            'from_name': 'GRC Nexus',
            'from_email': 'no-reply@everest.local',
            'timeout': '20',
            'notify_on_new': 'on',
        })
        self.assertRedirects(response, reverse('core:email_settings'))
        cfg = EmailSettings.get_solo()
        self.assertTrue(cfg.is_enabled)
        self.assertEqual(cfg.host, '192.168.56.10')
        self.assertEqual(cfg.password, 's3cret')
        self.assertNotIn('s3cret', cfg.password_encrypted)
        self.assertEqual(cfg.updated_by, self.superuser)

    def test_blank_password_keeps_the_existing_one(self):
        cfg = EmailSettings.get_solo()
        cfg.set_password('original')
        cfg.save()

        self.client.force_login(self.superuser)
        self.client.post(reverse('core:email_settings'), {
            'is_enabled': 'on',
            'host': '192.168.56.10',
            'port': '25',
            'security': 'none',
            'username': '',
            'password': '',
            'from_name': 'GRC Nexus',
            'from_email': 'no-reply@everest.local',
            'timeout': '20',
            'notify_on_new': 'on',
        })
        self.assertEqual(EmailSettings.get_solo().password, 'original')

    def test_test_send_requires_enabled_smtp(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse('core:send_smtp_test'), {
            'recipient': 'someone@everest.local',
        })
        self.assertRedirects(response, reverse('core:email_settings'))
        self.assertEqual(len(mail.outbox), 0)

    def test_test_send_rejects_invalid_address(self):
        cfg = EmailSettings.get_solo()
        cfg.is_enabled = True
        cfg.host = '192.168.56.10'
        cfg.save()

        self.client.force_login(self.superuser)
        self.client.post(reverse('core:send_smtp_test'), {
            'recipient': 'not-an-address',
        })
        self.assertEqual(len(mail.outbox), 0)

    def test_test_send_delivers(self):
        cfg = EmailSettings.get_solo()
        cfg.is_enabled = True
        cfg.host = '192.168.56.10'
        cfg.port = 25
        cfg.from_email = 'no-reply@everest.local'
        cfg.save()

        self.client.force_login(self.superuser)
        with mock.patch('core.emails.build_connection', locmem_connection):
            response = self.client.post(reverse('core:send_smtp_test'), {
                'recipient': 'someone@everest.local',
            })
        self.assertRedirects(response, reverse('core:email_settings'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['someone@everest.local'])


class NotificationEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Notify Dept')
        cls.other = Department.objects.create(name='Other Dept')
        cls.hod = User.objects.create_user(
            'notify_hod', 'hod@everest.local', 'pw',
            department=cls.dept, is_hod=True,
        )
        cls.named = User.objects.create_user(
            'notify_named', 'named@everest.local', 'pw',
            department=cls.dept,
        )
        cls.superuser = User.objects.create_superuser(
            'notify_admin', 'root@everest.local', 'pw',
        )

    def setUp(self):
        EmailSettings.objects.all().delete()
        mail.outbox = []
        self.cfg = EmailSettings.get_solo()
        self.cfg.is_enabled = True
        self.cfg.host = '192.168.56.10'
        self.cfg.port = 25
        self.cfg.security = 'none'
        self.cfg.from_name = 'GRC Nexus'
        self.cfg.from_email = 'no-reply@everest.local'
        self.cfg.notify_on_new = True
        self.cfg.save()

    def _notification(self, kind='risk_escalated', recipient=None, dept=None):
        return Notification.objects.create(
            owner_dept=dept or self.dept,
            recipient=recipient,
            kind=kind,
            title=f'Test {kind}',
            action_url='/notifications/',
        )

    def test_disabled_settings_send_nothing(self):
        self.cfg.is_enabled = False
        self.cfg.save()
        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_notification_email(self._notification())
        self.assertEqual(delivered, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_notify_switch_off_sends_nothing(self):
        self.cfg.notify_on_new = False
        self.cfg.save()
        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_notification_email(self._notification())
        self.assertEqual(delivered, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_routine_notification_stays_in_app(self):
        self.assertNotIn('asset_needs_owner', IMMEDIATE_KINDS)
        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_notification_email(
                self._notification(kind='asset_needs_owner'),
            )
        self.assertEqual(delivered, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_high_signal_notification_emails_the_hod(self):
        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_notification_email(self._notification())
        self.assertEqual(delivered, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['hod@everest.local'])
        self.assertIn('Test risk_escalated', mail.outbox[0].subject)

    def test_named_recipient_takes_precedence_over_hod(self):
        with mock.patch('core.emails.build_connection', locmem_connection):
            send_notification_email(self._notification(recipient=self.named))
        self.assertEqual(mail.outbox[0].to, ['named@everest.local'])

    def test_department_without_hod_falls_back_to_superusers(self):
        with mock.patch('core.emails.build_connection', locmem_connection):
            send_notification_email(self._notification(dept=self.other))
        self.assertEqual(mail.outbox[0].to, ['root@everest.local'])

    def test_user_can_opt_out_of_a_category(self):
        pref = UserPreference.get_for(self.hod)
        pref.email_on_risk_breach = False
        pref.save()

        with mock.patch('core.emails.build_connection', locmem_connection):
            delivered = send_notification_email(self._notification())
        self.assertEqual(delivered, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_create_notification_schedules_mail_after_commit(self):
        with mock.patch('core.emails.build_connection', locmem_connection):
            with self.captureOnCommitCallbacks(execute=True):
                notification = create_notification(
                    'risk_escalated',
                    'Risk beyond capacity',
                    '/risks/1/',
                    self.dept,
                )
        self.assertIsNotNone(notification)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['hod@everest.local'])

    def test_mail_failure_never_raises(self):
        def broken(*args, **kwargs):
            raise RuntimeError('smtp is down')

        with mock.patch('core.emails.build_connection', broken):
            delivered = send_notification_email(self._notification())
        self.assertEqual(delivered, 0)
