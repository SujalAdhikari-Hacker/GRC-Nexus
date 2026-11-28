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


class PdfReportsV330Tests(TestCase):
    """Verify v3.3.0 executive, operational, audit, and export PDF reports."""

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.dept_a = Department.objects.create(name='Security Operations')
        cls.dept_b = Department.objects.create(name='Finance Office')
        cls.superuser = User.objects.create_superuser(
            username='pdf_super',
            email='pdf-super@example.com',
            password='StrongPassword!123',
        )
        cls.user_b = User.objects.create_user(
            username='pdf_user_b',
            email='pdf-b@example.com',
            password='StrongPassword!123',
            department=cls.dept_b,
        )

        from assets.models import Asset
        from audits.models import Audit, AuditFinding, EvidenceItem, EvidenceVersion
        from incidents.models import Incident
        from risks.models import Risk, RiskCategory
        from tickets.models import Ticket
        from vendors.models import Vendor
        from vulnerabilities.models import Finding, Vulnerability

        cls.asset = Asset.objects.create(
            asset_id='AST-9001',
            name='Core Payment Gateway',
            description='Primary production payment processing gateway host.',
            owner_dept=cls.dept_a,
            criticality=4,
            rto_hours=48,
            rpo_hours=4,
            mtpd_hours=24,  # RTO > MTPD -> BIA gap
        )
        cat = RiskCategory.objects.create(name='Infrastructure Risk')
        cls.risk = Risk.objects.create(
            title='Critical Edge Gateway Exposure',
            category=cat,
            owner_dept=cls.dept_a,
            likelihood=4,
            impact=5,
            inherent_score=20,
            residual_score=20,
        )
        vuln = Vulnerability.objects.create(
            cve_id='CVE-2026-9001',
            title='Critical Authentication Bypass',
            cvss_score='9.8',
            cvss_severity='critical',
            kev_status=True,
        )
        cls.finding = Finding.objects.create(
            vulnerability=vuln,
            asset=cls.asset,
            owner_dept=cls.dept_a,
            discovered_date=today - timedelta(days=10),
            status='new',
        )
        cls.vendor = Vendor.objects.create(
            vendor_id='VEN-9001',
            name='CloudHost Alpha',
            owner_dept=cls.dept_a,
            tier=1,
            certifications=['ISO27001'],
            contract_renewal_date=today - timedelta(days=5),
            contact_email='security@cloudhost.example',
        )
        cls.incident = Incident.objects.create(
            title='Significant NIS2 Edge Intrusion',
            description='Detected suspicious edge intrusion attempt.',
            owner_dept=cls.dept_a,
            severity='critical',
            status='detected',
            nis2_significant=True,
            detected_at=timezone.now() - timedelta(hours=30),
        )
        cls.audit = Audit.objects.create(
            name='Annual ISO 27001 Audit',
            owner_dept=cls.dept_a,
        )
        cls.audit_finding = AuditFinding.objects.create(
            title='Privilege Review Evidence Missing',
            severity='high',
            status='open',
            audit=cls.audit,
            owner_dept=cls.dept_a,
            due_date=today - timedelta(days=2),
        )
        cls.ticket = Ticket.objects.create(
            title='Patch Edge Gateway Authentication',
            priority=4,
            status='open',
            owner_dept=cls.dept_a,
            due_date=today - timedelta(days=1),
        )
        cls.evidence = EvidenceItem.objects.create(
            title='Firewall Rule Export',
            audit=cls.audit,
            owner_dept=cls.dept_a,
        )
        EvidenceVersion.objects.create(
            evidence=cls.evidence,
            version=1,
            file_path='audit_evidence/fw_rules.json',
            file_name='fw_rules.json',
            size_bytes=512,
            sha256='deadbeef1234' + '0' * 52,
        )
        ServiceRun.objects.create(
            service='send_board_report',
            status='ok',
            message='Weekly digest completed',
        )

    def test_build_executive_report_includes_v330_metrics_and_scoping(self):
        ctx_super = build_executive_report(self.superuser)
        self.assertEqual(ctx_super['report_version'], 'v3.3.0')
        self.assertEqual(ctx_super['nis2_significant_count'], 1)
        self.assertEqual(ctx_super['nis2_breached_count'], 1)
        self.assertEqual(ctx_super['expired_contract_vendors'], 1)
        self.assertGreater(ctx_super['avg_vendor_score'], 0)
        self.assertEqual(ctx_super['bia_gap_count'], 1)
        self.assertEqual(ctx_super['rto_exceeds_mtpd_count'], 1)
        self.assertEqual(ctx_super['audit_findings_overdue'], 1)
        self.assertEqual(ctx_super['overdue_tickets'], 1)
        self.assertEqual(ctx_super['checksummed_evidence'], 1)
        self.assertTrue(ctx_super['chart_vendor_scores'])
        self.assertTrue(ctx_super['chart_bia'])
        self.assertTrue(ctx_super['service_health_rows'])

        # Department-scoped non-superuser must not see Dept A records or system ServiceRuns
        ctx_b = build_executive_report(self.user_b)
        self.assertEqual(ctx_b['nis2_significant_count'], 0)
        self.assertEqual(ctx_b['total_vendors'], 0)
        self.assertEqual(ctx_b['bia_gap_count'], 0)
        self.assertEqual(ctx_b['open_tickets'], 0)
        self.assertEqual(ctx_b['checksummed_evidence'], 0)
        self.assertEqual(ctx_b['service_health_rows'], [])

    def test_executive_report_html_contains_v330_content_and_true_sla_ladder(self):
        from django.template.loader import render_to_string

        ctx = build_executive_report(self.superuser)
        html = render_to_string('reports/executive_report.html', ctx)

        self.assertIn('v3.3.0', html)
        self.assertIn('img/logo.svg', html)
        self.assertIn('img/watermark_seal.png', html)
        self.assertIn('NIS2 Article 23', html)
        self.assertIn('Third-Party &amp; Vendor Assurance', html)
        self.assertIn('Business Continuity &amp; BIA Readiness', html)
        self.assertIn('CloudHost Alpha', html)
        self.assertIn('AST-9001', html)
        self.assertIn('RSK-', html)
        self.assertIn('High 14 days, Medium 30 days, Low 60 days, and Info/None 90 days', html)
        self.assertNotIn('high within 30, medium within 90, and low within 180', html)

    def test_all_updated_pdf_endpoints_return_valid_pdfs(self):
        self.client.force_login(self.superuser)

        endpoints = [
            reverse('core:executive_report'),
            reverse('risks:list') + '?format=pdf',
            reverse('vulnerabilities:finding_list') + '?format=pdf',
            reverse('assets:list') + '?format=pdf',
            reverse('audits:audit_report', args=[self.audit.pk]),
            reverse('core:data_export', args=['assets']) + '?format=pdf',
        ]
        for url in endpoints:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp['Content-Type'], 'application/pdf')
                self.assertTrue(resp.content.startswith(b'%PDF-'))
                self.assertGreater(len(resp.content), 2000)

    def test_audit_report_html_renders_evidence_sha256_and_sla_overdue(self):
        from django.template.loader import render_to_string

        self.evidence.latest_version = self.evidence.versions.first()
        html = render_to_string('reports/audit_report.html', {
            'audit': self.audit,
            'findings': [self.audit_finding],
            'tests': [],
            'evidence_items': [self.evidence],
            'generated_at': timezone.now(),
            'generated_by': self.superuser,
        })
        self.assertIn('img/logo.svg', html)
        self.assertIn('v3.3.0', html)
        self.assertIn('SLA Overdue', html)
        self.assertIn('deadbeef1234', html)
