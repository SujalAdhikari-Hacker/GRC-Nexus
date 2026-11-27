"""SLA clocks: the shared 7/14/30/60/90 ladder on findings and tickets."""
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from assets.models import Asset
from audits.models import AuditFinding
from core.models import Department
from core.sla import PRIORITY_TO_SEVERITY, SLA_DAYS, sla_due_date
from tickets.models import Ticket
from vulnerabilities.models import Finding, Vulnerability


class SlaLadderTests(SimpleTestCase):
    def test_the_ladder_is_7_14_30_60_90(self):
        self.assertEqual(SLA_DAYS, {
            'critical': 7, 'high': 14, 'medium': 30, 'low': 60, 'none': 90,
        })

    def test_due_date_is_start_plus_the_severity_days(self):
        start = date(2026, 1, 1)
        self.assertEqual(sla_due_date(start, 'critical'), date(2026, 1, 8))
        self.assertEqual(sla_due_date(start, 'high'), date(2026, 1, 15))
        self.assertEqual(sla_due_date(start, 'medium'), date(2026, 1, 31))
        self.assertEqual(sla_due_date(start, 'low'), date(2026, 3, 2))
        self.assertEqual(sla_due_date(start, 'none'), date(2026, 4, 1))

    def test_an_unknown_severity_gets_the_longest_clock(self):
        self.assertEqual(sla_due_date(date(2026, 1, 1), 'mystery'), date(2026, 4, 1))

    def test_ticket_priorities_map_to_the_same_ladder(self):
        self.assertEqual(PRIORITY_TO_SEVERITY, {
            4: 'critical', 3: 'high', 2: 'medium', 1: 'low',
        })


class SlaClockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='SLA Dept')

    def test_an_audit_finding_gets_a_severity_due_date(self):
        finding = AuditFinding.objects.create(
            title='Missing MFA', owner_dept=self.dept, severity='critical',
        )
        self.assertEqual(
            finding.due_date, timezone.localdate() + timedelta(days=7)
        )

    def test_an_explicit_audit_due_date_is_not_overwritten(self):
        target = timezone.localdate() + timedelta(days=2)
        finding = AuditFinding.objects.create(
            title='Explicit target', owner_dept=self.dept, severity='critical',
            due_date=target,
        )
        self.assertEqual(finding.due_date, target)

    def test_an_open_finding_past_its_sla_is_breached(self):
        finding = AuditFinding.objects.create(
            title='Past SLA', owner_dept=self.dept, severity='high',
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.assertTrue(finding.sla_breached)

    def test_a_resolved_finding_is_not_breached(self):
        finding = AuditFinding.objects.create(
            title='Resolved', owner_dept=self.dept, severity='high',
            status='resolved',
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.assertFalse(finding.sla_breached)

    def test_a_ticket_gets_a_priority_due_date(self):
        ticket = Ticket.objects.create(
            title='Patch the VPN', owner_dept=self.dept, priority=4,
        )
        self.assertEqual(
            ticket.due_date, timezone.localdate() + timedelta(days=7)
        )

    def test_an_explicit_ticket_due_date_is_not_overwritten(self):
        target = timezone.localdate() + timedelta(days=2)
        ticket = Ticket.objects.create(
            title='Explicit target', owner_dept=self.dept, priority=4,
            due_date=target,
        )
        self.assertEqual(ticket.due_date, target)

    def test_a_resolved_ticket_is_not_breached(self):
        ticket = Ticket.objects.create(
            title='Done', owner_dept=self.dept, priority=4, status='resolved',
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.assertFalse(ticket.sla_breached)

    def test_a_vulnerability_finding_uses_the_shared_ladder(self):
        asset = Asset.objects.create(
            name='SLA host', description='Host used for the SLA clock test',
            owner_dept=self.dept,
        )
        for severity, days in (
            ('critical', 7), ('high', 14), ('medium', 30), ('low', 60),
            ('none', 90),
        ):
            vulnerability = Vulnerability.objects.create(
                cve_id=f'CVE-2026-{severity}', title=f'{severity} test',
                cvss_severity=severity,
            )
            finding = Finding.objects.create(
                vulnerability=vulnerability, asset=asset,
                owner_dept=self.dept, discovered_date=date(2026, 1, 1),
            )
            self.assertEqual(
                finding.sla_due_date, date(2026, 1, 1) + timedelta(days=days)
            )

    def test_a_past_due_vulnerability_finding_is_breached(self):
        asset = Asset.objects.create(
            name='Breached host', description='Host used for the breach test',
            owner_dept=self.dept,
        )
        vulnerability = Vulnerability.objects.create(
            cve_id='CVE-2026-BREACH', title='Breach test', cvss_severity='high',
        )
        finding = Finding.objects.create(
            vulnerability=vulnerability, asset=asset, owner_dept=self.dept,
            discovered_date=timezone.localdate() - timedelta(days=30),
        )
        self.assertTrue(finding.sla_breached)
