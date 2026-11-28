"""Tests for the scheduled monthly executive PDF board-report pack."""
from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.executive_report import build_executive_report
from core.models import Department, OrganisationProfile, ServiceRun, User
from core.reports import render_pdf_bytes


class BoardReportPackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Executive Office')
        cls.superuser = User.objects.create_superuser(
            username='board_admin',
            email='board-admin@example.com',
            password='StrongPassword!123',
        )
        cls.normal_user = User.objects.create_user(
            username='board_viewer',
            email='viewer@example.com',
            password='StrongPassword!123',
            department=cls.dept,
        )

    def test_render_pdf_bytes_returns_valid_pdf_without_request(self):
        ctx = build_executive_report(self.superuser)
        pdf = render_pdf_bytes(
            'reports/executive_report.html',
            ctx,
            generated_by=self.superuser,
        )
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf), 5000)

    def test_command_sends_pdf_records_servicerun_and_enforces_monthly_window(self):
        org = OrganisationProfile.get()
        org.board_report_recipients = 'board@example.com, ciso@example.com'
        org.board_report_enabled = True
        org.save()

        out = StringIO()
        call_command('send_board_report', stdout=out)

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['board@example.com', 'ciso@example.com'])
        self.assertEqual(len(msg.attachments), 1)
        att_name, att_bytes, att_mime = msg.attachments[0]
        self.assertTrue(att_name.startswith('grcnexus_board_report_'))
        self.assertTrue(att_name.endswith('.pdf'))
        self.assertEqual(att_mime, 'application/pdf')
        self.assertTrue(bytes(att_bytes).startswith(b'%PDF-'))

        org.refresh_from_db()
        self.assertIsNotNone(org.last_board_report_sent_at)
        self.assertEqual(org.last_board_report_date, timezone.localdate())

        run = ServiceRun.objects.get(service='send_board_report')
        self.assertEqual(run.status, 'ok')
        self.assertEqual(run.counts.get('sent'), 1)

        # Immediate second run without --force is skipped by monthly cooldown
        call_command('send_board_report', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

        # --force sends even within the cooldown window
        call_command('send_board_report', force=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 2)

    def test_disabled_flag_and_dry_run_behave_cleanly(self):
        org = OrganisationProfile.get()
        org.board_report_enabled = False
        org.board_report_recipients = 'board@example.com'
        org.save()

        call_command('send_board_report', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

        call_command('send_board_report', force=True, dry_run=True, stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        org.refresh_from_db()
        self.assertIsNone(org.last_board_report_sent_at)
        self.assertFalse(ServiceRun.objects.filter(service='send_board_report', counts__sent=1).exists())

    def test_settings_send_now_view_superuser_only(self):
        url = reverse('core:send_board_report_now')
        self.client.force_login(self.normal_user)
        resp_forbidden = self.client.post(url)
        self.assertEqual(resp_forbidden.status_code, 403)

        self.client.force_login(self.superuser)
        resp_ok = self.client.post(url)
        self.assertRedirects(resp_ok, reverse('core:settings'))
        self.assertEqual(len(mail.outbox), 1)
