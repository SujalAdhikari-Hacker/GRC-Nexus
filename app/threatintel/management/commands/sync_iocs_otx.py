"""
Sync IOCs from AlienVault OTX.

Requires a free API key from https://otx.alienvault.com/
Set it as an environment variable: OTX_API_KEY=xxxxx

Usage:
    python manage.py sync_iocs_otx
    python manage.py sync_iocs_otx --pulses 20
    python manage.py sync_iocs_otx --api-key YOUR_KEY
"""
import os
from django.core.management.base import BaseCommand
from core.safe_http import safe_get
from django.utils import timezone

from threatintel.models import IOC, IOCFeedSync


API_URL = 'https://otx.alienvault.com/api/v1/pulses/subscribed'
HTTP_TIMEOUT = 60


TYPE_MAP = {
    'IPv4':      'ipv4',
    'IPv6':      'ipv6',
    'domain':    'domain',
    'hostname':  'domain',
    'URL':       'url',
    'URI':       'url',
    'FileHash-MD5':    'md5',
    'FileHash-SHA1':   'sha1',
    'FileHash-SHA256': 'sha256',
    'email':     'email',
    'CVE':       'cve',
    'Mutex':     'mutex',
    'FilePath':  'filepath',
    'WindowsRegistryKey': 'registry',
    'UserAgent': 'user_agent',
}


class Command(BaseCommand):
    help = 'Sync IOCs from AlienVault OTX (requires API key)'

    def add_arguments(self, parser):
        parser.add_argument('--pulses', type=int, default=20,
                            help='Number of recent pulses to fetch (default: 20)')
        parser.add_argument('--api-key', default=None,
                            help='OTX API key (or set OTX_API_KEY env var)')

    def handle(self, *args, **options):
        api_key = options['api_key'] or os.getenv('OTX_API_KEY', '')
        if not api_key:
            self.stdout.write(self.style.ERROR(
                'No API key. Get one free at https://otx.alienvault.com/ '
                'and either set OTX_API_KEY env var or use --api-key.'
            ))
            return

        sync_log = IOCFeedSync.objects.create(source='otx')

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Fetching up to {options["pulses"]} pulses from OTX...'
        ))

        try:
            r = safe_get(
                API_URL,
                headers={'X-OTX-API-KEY': api_key},
                params={'limit': options['pulses']},
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.finished_at = timezone.now()
            sync_log.save()
            self.stdout.write(self.style.ERROR(f'Fetch failed: {e}'))
            return

        pulses = data.get('results', [])
        self.stdout.write(f'  {len(pulses)} pulses fetched')

        created = 0
        updated = 0
        skipped = 0
        total_indicators = 0

        for pulse in pulses:
            pulse_name = pulse.get('name', '')
            pulse_tags = pulse.get('tags', []) or []
            malware_families = pulse.get('malware_families', []) or []

            for ind in pulse.get('indicators', []):
                total_indicators += 1
                value = (ind.get('indicator') or '').strip()
                if not value:
                    skipped += 1
                    continue

                our_type = TYPE_MAP.get(ind.get('type', ''), None)
                if not our_type:
                    skipped += 1
                    continue

                try:
                    obj, was_created = IOC.objects.update_or_create(
                        value=value[:500],
                        ioc_type=our_type,
                        source='otx',
                        defaults={
                            'threat_type': 'unknown',
                            'confidence': 2,
                            'source_id': str(pulse.get('id', ''))[:200],
                            'first_seen': ind.get('created'),
                            'tags': pulse_tags[:20],
                            'malware_family': (malware_families[0] if malware_families else '')[:200],
                            'is_active': True,
                            'notes': f'From pulse: {pulse_name[:200]}',
                        }
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception:
                    skipped += 1

        sync_log.finished_at = timezone.now()
        sync_log.items_fetched = total_indicators
        sync_log.items_created = created
        sync_log.items_updated = updated
        sync_log.items_skipped = skipped
        sync_log.status = 'completed'
        sync_log.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n✔ OTX sync complete.\n'
            f'  Pulses:     {len(pulses)}\n'
            f'  Indicators: {total_indicators}\n'
            f'  Created:    {created}\n'
            f'  Updated:    {updated}\n'
            f'  Skipped:    {skipped}'
        ))
