"""Raise NIS2 Article 23 deadline alerts.

Intended to run hourly, e.g.::

    docker compose exec -T web python manage.py sweep_nis2_deadlines

Safe to run as often as you like: each (incident, phase, kind) alert is
recorded once, so a repeated sweep never re-notifies.
"""
from django.core.management.base import BaseCommand

from incidents.services import sweep_deadlines


class Command(BaseCommand):
    help = (
        'Raise pre-deadline and breach alerts for NIS2 Article 23 incident '
        'reports (24 h / 72 h / 30 days).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be raised without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        result = sweep_deadlines(dry_run=dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing written.'))
            for item in result['dispatched']:
                self.stdout.write(
                    f"  · {item['reference']} {item['phase']} {item['kind']}"
                )
            self.stdout.write(
                f"{result['scanned']} incident(s) scanned; "
                f"{len(result['dispatched'])} alert(s) would be raised."
            )
            return

        self.stdout.write(
            f"Scanned {result['scanned']} incident(s); "
            f"{len(result['dispatched'])} new alert(s) raised."
        )
        self.stdout.write(self.style.SUCCESS('NIS2 deadline sweep complete.'))
