"""
Sync IOCs from ThreatCluster public feed. No API key needed.
"""
from django.core.management.base import BaseCommand
from core.safe_http import safe_get
from django.utils import timezone

from threatintel.models import IOC, IOCFeedSync


FEED_URL = 'https://threatcluster.io/api/iocs/public/feed.txt'
HTTP_TIMEOUT = 60


def _detect_type(value):
    v = value.strip()
    if not v:
        return None
    parts = v.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return 'ipv4'
    if ':' in v and not v.startswith('http'):
        return 'ipv6'
    if v.startswith('http://') or v.startswith('https://'):
        return 'url'
    if len(v) == 32 and all(c in '0123456789abcdef' for c in v.lower()):
        return 'md5'
    if len(v) == 40 and all(c in '0123456789abcdef' for c in v.lower()):
        return 'sha1'
    if len(v) == 64 and all(c in '0123456789abcdef' for c in v.lower()):
        return 'sha256'
    if '.' in v and ' ' not in v:
        return 'domain'
    return None


class Command(BaseCommand):
    help = 'Sync IOCs from ThreatCluster public feed (no auth key needed)'

    def handle(self, *args, **options):
        sync_log = IOCFeedSync.objects.create(source='manual')

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Fetching ThreatCluster public IOC feed...'
        ))

        try:
            r = safe_get(FEED_URL, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            lines = r.text.splitlines()
        except Exception as e:
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.finished_at = timezone.now()
            sync_log.save()
            self.stdout.write(self.style.ERROR(f'Fetch failed: {e}'))
            return

        values = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
        self.stdout.write(f'  Fetched {len(values)} indicators')

        created = 0
        updated = 0
        skipped = 0

        for value in values:
            ioc_type = _detect_type(value)
            if not ioc_type:
                skipped += 1
                continue
            try:
                obj, was_created = IOC.objects.update_or_create(
                    value=value[:500],
                    ioc_type=ioc_type,
                    source='threatcluster',
                    defaults={'threat_type': 'unknown', 'confidence': 2, 'is_active': True},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception:
                skipped += 1

        sync_log.finished_at = timezone.now()
        sync_log.items_fetched = len(values)
        sync_log.items_created = created
        sync_log.items_updated = updated
        sync_log.items_skipped = skipped
        sync_log.status = 'completed'
        sync_log.save()

        self.stdout.write(self.style.SUCCESS(
            f'\nThreatCluster sync complete.\n'
            f'  Fetched:  {len(values)}\n'
            f'  Created:  {created}\n'
            f'  Updated:  {updated}\n'
            f'  Skipped:  {skipped}\n'
            f'  Total IOCs in DB: {IOC.objects.count()}'
        ))
