"""
Sync recent IOCs from abuse.ch ThreatFox.

Free, no API key. Returns recent malware IOCs (IPs, domains, URLs, hashes).

Usage:
    python manage.py sync_iocs_threatfox
    python manage.py sync_iocs_threatfox --days 7
    python manage.py sync_iocs_threatfox --days 30
"""
import requests
from datetime import datetime, timezone as dt_timezone
from django.core.management.base import BaseCommand
from django.utils import timezone

from threatintel.models import IOC, IOCFeedSync


API_URL = 'https://threatfox-api.abuse.ch/api/v1/'
HTTP_TIMEOUT = 60


# Map ThreatFox threat_type → our choices
THREAT_TYPE_MAP = {
    'botnet_cc':     'c2',
    'payload_delivery': 'malware',
    'payload':       'malware',
    'malware':       'malware',
    'ransomware':    'ransomware',
    'phishing':      'phishing',
    'exploit':       'exploit',
}


def _detect_ioc_type(value):
    """Guess our IOC type from the ThreatFox string format."""
    if ':' in value and not value.startswith('http'):
        # ip:port or domain:port
        host = value.split(':')[0]
        if all(c.isdigit() or c == '.' for c in host):
            return 'ipv4'
        return 'domain'
    if value.startswith('http://') or value.startswith('https://'):
        return 'url'
    if len(value) == 32 and all(c in '0123456789abcdef' for c in value.lower()):
        return 'md5'
    if len(value) == 40 and all(c in '0123456789abcdef' for c in value.lower()):
        return 'sha1'
    if len(value) == 64 and all(c in '0123456789abcdef' for c in value.lower()):
        return 'sha256'
    if '.' in value:
        return 'domain'
    return 'unknown'


def _parse_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S UTC', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=dt_timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


class Command(BaseCommand):
    help = 'Sync recent IOCs from abuse.ch ThreatFox'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=3,
                            help='How many days back (default: 3, max: 7)')

    def handle(self, *args, **options):
        days = min(max(options['days'], 1), 7)  # ThreatFox caps at 7 days

        sync_log = IOCFeedSync.objects.create(source='threatfox')

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Syncing ThreatFox IOCs (last {days} days)...'
        ))

        try:
            r = requests.post(
                API_URL,
                json={'query': 'get_iocs', 'days': days},
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

        if data.get('query_status') != 'ok':
            sync_log.status = 'failed'
            sync_log.error_message = f"query_status = {data.get('query_status')}"
            sync_log.finished_at = timezone.now()
            sync_log.save()
            self.stdout.write(self.style.ERROR(f"API returned: {data.get('query_status')}"))
            return

        items = data.get('data', [])
        self.stdout.write(f'  Fetched {len(items)} IOCs')

        created = 0
        updated = 0
        skipped = 0

        for item in items:
            value = item.get('ioc', '').strip()
            if not value:
                skipped += 1
                continue

            ioc_type = _detect_ioc_type(value)
            if ioc_type == 'unknown':
                skipped += 1
                continue

            threat_type = THREAT_TYPE_MAP.get(item.get('threat_type', ''), 'unknown')

            # Confidence: ThreatFox gives 0-100, map to our 1-4
            conf_raw = item.get('confidence_level', 50)
            if conf_raw >= 90:
                confidence = 4
            elif conf_raw >= 70:
                confidence = 3
            elif conf_raw >= 40:
                confidence = 2
            else:
                confidence = 1

            try:
                obj, was_created = IOC.objects.update_or_create(
                    value=value,
                    ioc_type=ioc_type,
                    source='threatfox',
                    defaults={
                        'threat_type': threat_type,
                        'confidence': confidence,
                        'source_id': str(item.get('id', '')),
                        'first_seen': _parse_date(item.get('first_seen_utc')),
                        'last_seen': _parse_date(item.get('last_seen_utc')),
                        'malware_family': item.get('malware_printable', '') or item.get('malware', ''),
                        'tags': item.get('tags') or [],
                        'is_active': True,
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Failed {value[:50]}: {e}'))
                skipped += 1

        sync_log.finished_at = timezone.now()
        sync_log.items_fetched = len(items)
        sync_log.items_created = created
        sync_log.items_updated = updated
        sync_log.items_skipped = skipped
        sync_log.status = 'completed'
        sync_log.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n✔ ThreatFox sync complete.\n'
            f'  Fetched:  {len(items)}\n'
            f'  Created:  {created}\n'
            f'  Updated:  {updated}\n'
            f'  Skipped:  {skipped}\n'
            f'  Total IOCs in DB: {IOC.objects.count()}'
        ))
