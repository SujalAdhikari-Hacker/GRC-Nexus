"""Tests for CSV and JSON scanner output import into vulnerability findings."""
import json
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import Asset
from core.models import Department, User
from vulnerabilities.models import Finding, Vulnerability
from vulnerabilities.scanner_import import import_scanner_upload


class ScannerImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept_a = Department.objects.create(name='IT Security')
        cls.dept_b = Department.objects.create(name='Finance')
        cls.user_a = User.objects.create_user(
            username='sec_importer', password='StrongPassword!123', department=cls.dept_a, is_hod=True,
        )
        cls.user_b = User.objects.create_user(
            username='fin_user', password='StrongPassword!123', department=cls.dept_b,
        )
        cls.asset_a = Asset.objects.create(
            name='Edge Firewall',
            description='Primary perimeter firewall protecting production.',
            owner_dept=cls.dept_a,
            ip_address='10.10.1.5',
            hostname='fw-edge-01',
            criticality=4,
        )
        cls.asset_b = Asset.objects.create(
            name='Finance ERP',
            description='Finance accounting database server.',
            owner_dept=cls.dept_b,
            ip_address='10.20.1.9',
            hostname='fin-erp-01',
            criticality=4,
        )

    def test_csv_import_creates_and_updates_idempotently(self):
        csv_body = (
            'CVE,Plugin Name,Host,Port,Risk Factor,CVSS3 Base Score,Plugin Output,Solution\n'
            'CVE-2025-1111,OpenSSL Heap Overflow,10.10.1.5,443/tcp,Critical,9.8,Detected OpenSSL 3.0.1,Upgrade to 3.0.15\n'
        ).encode('utf-8')
        upload = SimpleUploadedFile('nessus.csv', csv_body, content_type='text/csv')
        res1 = import_scanner_upload(upload, self.user_a, scanner_label='Nessus')

        self.assertEqual(res1['created'], 1)
        self.assertEqual(res1['updated'], 0)
        self.assertEqual(res1['skipped'], 0)

        vuln = Vulnerability.objects.get(cve_id='CVE-2025-1111')
        self.assertEqual(vuln.source, 'scanner')
        finding = Finding.objects.get(vulnerability=vuln, asset=self.asset_a, port='443/tcp')
        self.assertEqual(finding.sla_due_date, timezone.localdate() + timedelta(days=7))
        self.assertIn('[Scanner: Nessus]', finding.evidence)

        # Re-importing same finding updates rather than duplicating
        csv_body_2 = (
            'CVE,Plugin Name,Host,Port,Risk Factor,CVSS3 Base Score,Plugin Output,Solution\n'
            'CVE-2025-1111,OpenSSL Heap Overflow,10.10.1.5,443/tcp,Critical,9.8,Re-verified OpenSSL 3.0.1,Upgrade to 3.0.16\n'
        ).encode('utf-8')
        upload2 = SimpleUploadedFile('nessus.csv', csv_body_2, content_type='text/csv')
        res2 = import_scanner_upload(upload2, self.user_a, scanner_label='Nessus')
        self.assertEqual(res2['created'], 0)
        self.assertEqual(res2['updated'], 1)
        self.assertEqual(Finding.objects.filter(vulnerability=vuln, asset=self.asset_a).count(), 1)
        finding.refresh_from_db()
        self.assertEqual(finding.solution, 'Upgrade to 3.0.16')

    def test_json_flat_trivy_and_sarif_imports(self):
        flat = json.dumps([
            {
                'cve_id': 'CVE-2025-2222',
                'title': 'TLS weak cipher',
                'asset': 'fw-edge-01',
                'severity': 'medium',
                'cvss': 5.3,
                'port': '8443',
            }
        ]).encode('utf-8')
        res_flat = import_scanner_upload(SimpleUploadedFile('flat.json', flat), self.user_a)
        self.assertEqual(res_flat['created'], 1)

        trivy = json.dumps({
            'Results': [{
                'Target': self.asset_a.asset_id,
                'Vulnerabilities': [{
                    'VulnerabilityID': 'CVE-2025-3333',
                    'PkgName': 'curl',
                    'InstalledVersion': '7.88',
                    'FixedVersion': '8.4',
                    'Severity': 'HIGH',
                    'Title': 'curl SOCKS5 heap buffer overflow',
                    'CVSS': {'nvd': {'V3Score': 8.8}},
                }],
            }],
        }).encode('utf-8')
        res_trivy = import_scanner_upload(SimpleUploadedFile('trivy.json', trivy), self.user_a)
        self.assertEqual(res_trivy['created'], 1)

        sarif = json.dumps({
            'version': '2.1.0',
            'runs': [{
                'tool': {'driver': {'rules': [{
                    'id': 'CVE-2025-4444',
                    'shortDescription': {'text': 'Exposed admin endpoint'},
                    'properties': {'security-severity': '6.5'},
                }]}},
                'results': [{
                    'ruleId': 'CVE-2025-4444',
                    'level': 'warning',
                    'message': {'text': 'Admin endpoint reachable on port 8080'},
                    'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'fw-edge-01'}}}],
                }],
            }],
        }).encode('utf-8')
        res_sarif = import_scanner_upload(SimpleUploadedFile('report.json', sarif), self.user_a)
        self.assertEqual(res_sarif['created'], 1)
        self.assertEqual(Finding.objects.filter(asset=self.asset_a).count(), 3)

    def test_cross_department_asset_is_blocked_and_fallback_asset_works(self):
        payload = json.dumps([
            {'cve_id': 'CVE-2025-5555', 'title': 'Cross dept', 'asset': '10.20.1.9', 'severity': 'high'},
            {'cve_id': 'CVE-2025-6666', 'title': 'Fallback host', 'severity': 'low'},
        ]).encode('utf-8')
        res = import_scanner_upload(
            SimpleUploadedFile('scan.json', payload),
            self.user_a,
            default_asset=self.asset_a,
        )
        self.assertEqual(res['created'], 1)
        self.assertEqual(res['skipped'], 1)
        self.assertFalse(Finding.objects.filter(asset=self.asset_b).exists())
        self.assertTrue(
            Finding.objects.filter(asset=self.asset_a, vulnerability__cve_id='CVE-2025-6666').exists()
        )

    def test_invalid_file_inputs_return_clean_errors(self):
        bad_ext = SimpleUploadedFile('scan.xml', b'<xml/>')
        self.assertIn('error', import_scanner_upload(bad_ext, self.user_a))

        bad_json = SimpleUploadedFile('scan.json', b'{not valid json')
        self.assertIn('error', import_scanner_upload(bad_json, self.user_a))

        huge = SimpleUploadedFile('scan.csv', b'x' * (5 * 1024 * 1024 + 10))
        self.assertIn('error', import_scanner_upload(huge, self.user_a))

    def test_view_get_and_post_upload(self):
        self.client.force_login(self.user_a)
        url = reverse('vulnerabilities:scanner_import')
        resp_get = self.client.get(url)
        self.assertEqual(resp_get.status_code, 200)

        upload = SimpleUploadedFile(
            'openvas.csv',
            b'cve,title,host,severity,cvss\nCVE-2025-7777,SSH Weak KEX,fw-edge-01,medium,5.0\n',
            content_type='text/csv',
        )
        resp_post = self.client.post(url, {'file': upload, 'scanner_label': 'OpenVAS'})
        self.assertEqual(resp_post.status_code, 200)
        self.assertTrue(
            Finding.objects.filter(asset=self.asset_a, vulnerability__cve_id='CVE-2025-7777').exists()
        )
