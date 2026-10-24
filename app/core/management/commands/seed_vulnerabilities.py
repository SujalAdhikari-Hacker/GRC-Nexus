from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assets.models import Asset
from vulnerabilities.models import Vulnerability, Finding


class Command(BaseCommand):
    help = 'Seed demo vulnerability and finding data'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding vulnerabilities...'))

        today = timezone.localdate()

        # (cve_id, title, cvss, severity, epss, kev, published)
        vulns = [
            ('CVE-2024-3400',  'PAN-OS GlobalProtect Command Injection',      10.0, 'critical', 0.94, True,  today - timedelta(days=180)),
            ('CVE-2024-21762', 'Fortinet SSL VPN Out-of-Bounds Write',         9.6,  'critical', 0.92, True,  today - timedelta(days=210)),
            ('CVE-2023-4966',  'Citrix Bleed Session Token Leak',              9.4,  'critical', 0.91, True,  today - timedelta(days=380)),
            ('CVE-2024-4577',  'PHP CGI Argument Injection',                   9.8,  'critical', 0.88, False, today - timedelta(days=150)),
            ('CVE-2024-3094',  'XZ Utils Backdoor',                           10.0, 'critical', 0.35, False, today - timedelta(days=200)),
            ('CVE-2024-6387',  'RegreSSHion — OpenSSH Signal Handler RCE',     8.1,  'high',     0.72, False, today - timedelta(days=90)),
            ('CVE-2023-44487', 'HTTP/2 Rapid Reset DoS',                       7.5,  'high',     0.85, True,  today - timedelta(days=340)),
            ('CVE-2023-34362', 'MOVEit Transfer SQL Injection',                9.8,  'critical', 0.89, True,  today - timedelta(days=440)),
            ('CVE-2024-21413', 'Microsoft Outlook RCE (MonikerLink)',          9.8,  'critical', 0.55, False, today - timedelta(days=240)),
            ('CVE-2024-1086',  'Linux Kernel Netfilter Use-After-Free LPE',    7.8,  'high',     0.60, False, today - timedelta(days=270)),
        ]

        created_vulns = {}
        for cve_id, title, cvss, sev, epss, kev, pub in vulns:
            vuln, created = Vulnerability.objects.get_or_create(
                cve_id=cve_id,
                defaults={
                    'title': title,
                    'description': f'{title}. See NVD for details.',
                    'cvss_score': cvss,
                    'cvss_severity': sev,
                    'epss_score': epss,
                    'epss_percentile': min(epss + 0.05, 0.99),
                    'kev_status': kev,
                    'published_date': pub,
                    'references': f'https://nvd.nist.gov/vuln/detail/{cve_id}',
                }
            )
            created_vulns[cve_id] = vuln
            if created:
                self.stdout.write(f"  Vuln: {cve_id}")

        # (cve_id, asset_name, status, port, discovered_offset_days)
        findings = [
            ('CVE-2024-3400',  'Firewall - Perimeter',        'open',        '443',  15),
            ('CVE-2024-21762', 'Firewall - Perimeter',        'in_progress', '10443', 22),
            ('CVE-2023-4966',  'Web Application Server',      'open',        '443',  45),
            ('CVE-2024-4577',  'Web Application Server',      'in_progress', '80',   30),
            ('CVE-2024-3094',  'Database Server',             'open',        '',     60),
            ('CVE-2024-6387',  'Web Application Server',      'open',        '22',   12),
            ('CVE-2024-6387',  'Database Server',             'remediated',  '22',   90),
            ('CVE-2023-44487', 'Web Application Server',      'open',        '443',  40),
            ('CVE-2023-34362', 'Payroll System',              'open',        '443',  75),
            ('CVE-2024-21413', 'Employee Laptops (batch)',    'in_progress', '',     35),
            ('CVE-2024-1086',  'Database Server',             'open',        '',     50),
            ('CVE-2024-1086',  'Web Application Server',      'open',        '',     50),
        ]

        created_count = 0
        for cve_id, asset_name, status, port, days_ago in findings:
            try:
                asset = Asset.objects.get(name=asset_name)
            except Asset.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  Skipping — asset not found: {asset_name}"))
                continue

            vuln = created_vulns.get(cve_id)
            if not vuln:
                continue

            remediated = (today - timedelta(days=days_ago - 5)) if status == 'remediated' else None

            finding, created = Finding.objects.get_or_create(
                vulnerability=vuln,
                asset=asset,
                port=port,
                defaults={
                    'owner_dept': asset.owner_dept,
                    'status': status,
                    'discovered_date': today - timedelta(days=days_ago),
                    'remediated_date': remediated,
                    'evidence': f'Auto-discovered via scan. CVE: {cve_id}. Port: {port or "N/A"}.',
                    'remediation_notes': '' if status == 'open' else f'Status: {status}.',
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Finding: {cve_id} on {asset_name}")

        self.stdout.write(self.style.SUCCESS('\n✔ Vulnerability seed complete.\n'))
        self.stdout.write(f"  Vulnerabilities:  {Vulnerability.objects.count()}")
        self.stdout.write(f"  Findings:         {Finding.objects.count()}")
        self.stdout.write(f"  Open findings:    {Finding.objects.filter(status='open').count()}")
        self.stdout.write(f"  KEV findings:     {Finding.objects.filter(vulnerability__kev_status=True).count()}")
