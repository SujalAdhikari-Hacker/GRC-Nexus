"""
Sync recent CVEs from NVD API 2.0.

NVD rate limits: 5 requests per 30 seconds without API key.
We use a 7-second delay between page requests to stay safe.

Usage:
    python manage.py sync_recent_cves              # last 7 days
    python manage.py sync_recent_cves --days 30    # last 30 days
    python manage.py sync_recent_cves --days 1     # last 24 hours
"""
import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from core.safe_http import safe_get
from vulnerabilities.models import Vulnerability


NVD_URL = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
NVD_PAGE_SIZE = 2000
REQUEST_DELAY = 7  # seconds between requests (safe under 5 req / 30s limit)
HTTP_TIMEOUT = 30


def _parse_cvss(metrics):
    """Extract CVSS score + vector + severity from NVD metrics block."""
    for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
        if key in metrics and metrics[key]:
            m = metrics[key][0]['cvssData']
            score = m.get('baseScore')
            vector = m.get('vectorString', '')
            sev = m.get('baseSeverity', '').lower() or None
            return score, vector, sev
    return None, '', None


def _severity_from_score(score):
    if score is None:
        return 'medium'
    if score >= 9.0:
        return 'critical'
    if score >= 7.0:
        return 'high'
    if score >= 4.0:
        return 'medium'
    if score > 0:
        return 'low'
    return 'none'


class Command(BaseCommand):
    help = 'Sync recent CVEs from NVD API into the local Vulnerability table'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7,
                            help='How many days back to fetch (default: 7)')
        parser.add_argument('--max-pages', type=int, default=5,
                            help='Safety cap on number of pages (default: 5 = 10000 CVEs)')

    def handle(self, *args, **options):
        days = options['days']
        max_pages = options['max_pages']

        end = timezone.now()
        start = end - timedelta(days=days)

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S.000')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S.000')

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Syncing CVEs from {start.date()} to {end.date()}...'
        ))

        created = 0
        updated = 0
        skipped = 0
        offset = 0
        page = 0

        while page < max_pages:
            page += 1
            self.stdout.write(f'  Fetching page {page} (offset {offset})...')

            try:
                r = safe_get(NVD_URL, params={
                    'pubStartDate': start_str,
                    'pubEndDate': end_str,
                    'resultsPerPage': NVD_PAGE_SIZE,
                    'startIndex': offset,
                }, headers={'User-Agent': 'GRC Nexus-GRC/1.0'},
                    timeout=HTTP_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  NVD fetch failed: {e}'))
                break

            items = data.get('vulnerabilities', [])
            total_results = data.get('totalResults', 0)

            if not items:
                break

            for item in items:
                cve = item.get('cve', {})
                cve_id = cve.get('id')
                if not cve_id:
                    continue

                # Skip 'REJECTED' records
                status = cve.get('vulnStatus', '').lower()
                if 'rejected' in status:
                    skipped += 1
                    continue

                metrics = cve.get('metrics', {})
                cvss, vector, sev = _parse_cvss(metrics)
                if not sev:
                    sev = _severity_from_score(cvss)

                # Description
                desc = ''
                for d in cve.get('descriptions', []):
                    if d.get('lang') == 'en':
                        desc = d.get('value', '')
                        break

                # Published date
                pub = cve.get('published', '')
                pub_date = None
                if pub:
                    try:
                        pub_date = datetime.fromisoformat(pub.replace('Z', '+00:00')).date()
                    except Exception:
                        pass

                # References
                refs = '\n'.join(
                    ref.get('url', '') for ref in cve.get('references', [])
                )

                try:
                    with transaction.atomic():
                        obj, was_created = Vulnerability.objects.update_or_create(
                            cve_id=cve_id,
                            defaults={
                                'title': (desc[:300] if desc else cve_id),
                                'description': desc,
                                'cvss_score': cvss or 0,
                                'cvss_vector': vector,
                                'cvss_severity': sev,
                                'published_date': pub_date,
                                'references': refs,
                                'source': 'nvd',
                                'last_enriched': timezone.now(),
                            }
                        )
                        if was_created:
                            created += 1
                        else:
                            updated += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  Failed {cve_id}: {e}'))

            offset += len(items)

            if offset >= total_results:
                break

            # Rate limit
            time.sleep(REQUEST_DELAY)

        self.stdout.write(self.style.SUCCESS(
            f'\nSync complete: {created} created, {updated} updated, {skipped} rejected/skipped.'
        ))
        self.stdout.write(f'Total CVEs in database: {Vulnerability.objects.count()}')
