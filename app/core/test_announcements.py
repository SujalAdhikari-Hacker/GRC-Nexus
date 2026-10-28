"""Tests for sending notifications from the app.

Run with:
    python manage.py test core.test_announcements
"""
from unittest import mock

from django.core import mail
from django.core.mail import get_connection
from django.test import TestCase
from django.urls import reverse

from core.announcements import (
    AUDIENCE_ALL,
    AUDIENCE_DEPARTMENTS,
    AUDIENCE_MY_DEPARTMENT,
    AUDIENCE_USERS,
    allowed_audiences,
    resolve_targets,
    send_announcement,
)
from core.models import Department, User
from core.notification_forms import NotificationComposeForm
from core.notifications import Notification
from core.settings_model import EmailSettings, UserPreference


def locmem_connection(*args, **kwargs):
    return get_connection('django.core.mail.backends.locmem.EmailBackend')


class AnnouncementTestCase(TestCase):
    def setUp(self):
        self.eng = Department.objects.create(name='Engineering')
        self.fin = Department.objects.create(name='Finance')
        self.superuser = User.objects.create_user(
            'root', 'root@everest.local', 'pw', is_superuser=True, is_staff=True,
        )
        self.hod = User.objects.create_user(
            'hod', 'hod@everest.local', 'pw',
            department=self.eng, is_hod=True,
        )
        self.eng_user = User.objects.create_user(
            'eng1', 'eng1@everest.local', 'pw', department=self.eng,
        )
        self.fin_user = User.objects.create_user(
            'fin1', 'fin1@everest.local', 'pw', department=self.fin,
        )
        self.lonely = User.objects.create_user('lonely', 'lonely@everest.local', 'pw')

    def compose(self, user, **overrides):
        data = {
            'title': 'Phishing drill Friday',
            'body': 'Be ready at 10:00.',
            'audience': AUDIENCE_MY_DEPARTMENT,
            'send_email': '',
        }
        data.update(overrides)
        return NotificationComposeForm(data, user=user)


class AudienceTests(AnnouncementTestCase):
    def test_superuser_can_address_every_audience(self):
        self.assertEqual(
            allowed_audiences(self.superuser),
            [AUDIENCE_ALL, AUDIENCE_DEPARTMENTS, AUDIENCE_USERS],
        )

    def test_hod_is_limited_to_own_department_and_people(self):
        self.assertEqual(
            allowed_audiences(self.hod),
            [AUDIENCE_MY_DEPARTMENT, AUDIENCE_USERS],
        )

    def test_all_departments_creates_one_row_each(self):
        created = send_announcement(
            self.superuser, 'Org-wide notice', audience=AUDIENCE_ALL,
        )
        self.assertEqual(len(created), Department.objects.count())
        self.assertTrue(all(n.owner_dept_id for n in created))
        self.assertTrue(all(n.recipient_id is None for n in created))

    def test_hod_cannot_address_all_departments(self):
        with self.assertRaises(PermissionError):
            resolve_targets(self.hod, AUDIENCE_ALL)

    def test_hod_cannot_address_another_department(self):
        with self.assertRaises(PermissionError):
            resolve_targets(self.hod, AUDIENCE_DEPARTMENTS, departments=[self.fin])

    def test_direct_message_has_no_department(self):
        pairs = resolve_targets(self.hod, AUDIENCE_USERS, users=[self.eng_user])
        self.assertEqual(pairs, [(None, self.eng_user)])

    def test_hod_cannot_target_someone_outside_their_department(self):
        pairs = resolve_targets(self.hod, AUDIENCE_USERS, users=[self.fin_user])
        self.assertEqual(pairs, [])


class ComposeFormTests(AnnouncementTestCase):
    def test_hod_department_message_is_valid(self):
        form = self.compose(self.hod)
        self.assertTrue(form.is_valid(), form.errors)

    def test_hod_cannot_force_org_wide_by_posting_all(self):
        form = self.compose(self.hod, audience=AUDIENCE_ALL)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_hod_cannot_select_another_department(self):
        form = self.compose(
            self.hod, audience=AUDIENCE_DEPARTMENTS, departments=[self.fin.pk],
        )
        self.assertFalse(form.is_valid())
        self.assertIn('departments', form.errors)

    def test_hod_cannot_select_another_departments_user(self):
        form = self.compose(
            self.hod, audience=AUDIENCE_USERS, users=[self.fin_user.pk],
        )
        self.assertFalse(form.is_valid())
        self.assertIn('users', form.errors)

    def test_departments_audience_requires_a_selection(self):
        form = self.compose(self.superuser, audience=AUDIENCE_DEPARTMENTS)
        self.assertFalse(form.is_valid())
        self.assertIn('departments', form.errors)

    def test_users_audience_requires_a_selection(self):
        form = self.compose(self.superuser, audience=AUDIENCE_USERS)
        self.assertFalse(form.is_valid())
        self.assertIn('users', form.errors)

    def test_superuser_without_department_cannot_pick_my_department(self):
        form = self.compose(self.superuser)
        self.assertFalse(form.is_valid())
        self.assertIn('audience', form.errors)


class DeliveryTests(AnnouncementTestCase):
    def test_department_message_is_visible_to_that_department_only(self):
        send_announcement(self.hod, 'Eng only', audience=AUDIENCE_MY_DEPARTMENT)

        self.client.force_login(self.eng_user)
        response = self.client.get(reverse('core:notifications'))
        self.assertContains(response, 'Eng only')

        self.client.force_login(self.fin_user)
        response = self.client.get(reverse('core:notifications'))
        self.assertNotContains(response, 'Eng only')

    def test_direct_message_is_visible_to_the_named_person_only(self):
        send_announcement(
            self.superuser, 'For you', audience=AUDIENCE_USERS,
            users=[self.eng_user],
        )

        self.client.force_login(self.eng_user)
        self.assertContains(
            self.client.get(reverse('core:notifications')), 'For you',
        )

        self.client.force_login(self.hod)
        self.assertNotContains(
            self.client.get(reverse('core:notifications')), 'For you',
        )

    def test_person_without_department_still_sees_a_direct_message(self):
        send_announcement(
            self.superuser, 'Hello lonely', audience=AUDIENCE_USERS,
            users=[self.lonely],
        )

        self.client.force_login(self.lonely)
        response = self.client.get(reverse('core:notifications'))
        self.assertContains(response, 'Hello lonely')
        self.assertEqual(response.context['unread_notification_count'], 1)

    def test_announcement_is_not_auto_cleared_by_the_sweep(self):
        send_announcement(self.hod, 'Sticky', audience=AUDIENCE_MY_DEPARTMENT)
        self.client.force_login(self.eng_user)
        self.client.get(reverse('core:notifications'))
        self.client.get(reverse('core:notifications'))
        self.assertEqual(Notification.objects.filter(kind='announcement').count(), 1)

    def test_sender_and_body_are_stored(self):
        created = send_announcement(
            self.hod, 'Title', body='Body text', audience=AUDIENCE_MY_DEPARTMENT,
        )
        notification = created[0]
        self.assertEqual(notification.body, 'Body text')
        self.assertEqual(notification.sent_by, self.hod)
        self.assertEqual(notification.kind, 'announcement')


class ComposeViewTests(AnnouncementTestCase):
    def test_hod_can_open_the_form(self):
        self.client.force_login(self.hod)
        response = self.client.get(reverse('core:notification_compose'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Send a notification')

    def test_regular_user_is_refused(self):
        self.client.force_login(self.eng_user)
        response = self.client.get(reverse('core:notification_compose'))
        self.assertEqual(response.status_code, 403)

    def test_hod_post_creates_one_notification_for_their_department(self):
        self.client.force_login(self.hod)
        response = self.client.post(reverse('core:notification_compose'), {
            'title': 'Mandatory training',
            'body': 'Complete it by Friday.',
            'audience': AUDIENCE_MY_DEPARTMENT,
        })
        self.assertRedirects(response, reverse('core:notifications'))
        notification = Notification.objects.get(kind='announcement')
        self.assertEqual(notification.owner_dept, self.eng)
        self.assertEqual(notification.sent_by, self.hod)

    def test_superuser_post_to_two_people_creates_two_rows(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse('core:notification_compose'), {
            'title': 'Hi both',
            'audience': AUDIENCE_USERS,
            'users': [self.eng_user.pk, self.fin_user.pk],
        })
        self.assertRedirects(response, reverse('core:notifications'))
        self.assertEqual(
            Notification.objects.filter(kind='announcement').count(), 2,
        )

    def test_hod_without_department_is_redirected(self):
        lonely_hod = User.objects.create_user(
            'hodless', 'hodless@everest.local', 'pw', is_hod=True,
        )
        self.client.force_login(lonely_hod)
        response = self.client.get(reverse('core:notification_compose'))
        self.assertRedirects(response, reverse('core:notifications'))


class AnnouncementEmailTests(AnnouncementTestCase):
    def setUp(self):
        super().setUp()
        EmailSettings.objects.all().delete()
        cfg = EmailSettings.get_solo()
        cfg.is_enabled = True
        cfg.host = '192.168.56.10'
        cfg.port = 25
        cfg.security = 'none'
        cfg.from_email = 'no-reply@everest.local'
        cfg.from_name = 'GRC Nexus'
        cfg.save()

    @mock.patch('core.emails.build_connection', locmem_connection)
    def test_email_copy_reaches_the_department(self):
        with self.captureOnCommitCallbacks(execute=True):
            send_announcement(
                self.superuser, 'Drill', body='At 10:00',
                audience=AUDIENCE_DEPARTMENTS, departments=[self.eng],
                email=True,
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(
            mail.outbox[0].to, ['hod@everest.local', 'eng1@everest.local'],
        )
        self.assertIn('Drill', mail.outbox[0].subject)

    @mock.patch('core.emails.build_connection', locmem_connection)
    def test_opt_out_is_honoured(self):
        UserPreference.objects.create(
            user=self.eng_user, email_notifications_enabled=False,
        )
        with self.captureOnCommitCallbacks(execute=True):
            send_announcement(
                self.superuser, 'Drill',
                audience=AUDIENCE_DEPARTMENTS, departments=[self.eng],
                email=True,
            )

        self.assertEqual(mail.outbox[0].to, ['hod@everest.local'])

    @mock.patch('core.emails.build_connection', locmem_connection)
    def test_no_email_when_the_box_is_unticked(self):
        with self.captureOnCommitCallbacks(execute=True):
            send_announcement(
                self.superuser, 'Drill',
                audience=AUDIENCE_DEPARTMENTS, departments=[self.eng],
                email=False,
            )

        self.assertEqual(mail.outbox, [])

    @mock.patch('core.emails.build_connection', locmem_connection)
    def test_no_email_when_smtp_is_disabled(self):
        cfg = EmailSettings.get_solo()
        cfg.is_enabled = False
        cfg.save()

        with self.captureOnCommitCallbacks(execute=True):
            send_announcement(
                self.superuser, 'Drill',
                audience=AUDIENCE_DEPARTMENTS, departments=[self.eng],
                email=True,
            )

        self.assertEqual(mail.outbox, [])
