"""Propose cross-framework equivalents for the mappings that already exist.

New mappings propagate as they are created; this backfills the ones recorded
before that behaviour existed. Idempotent: a pair that already has a mapping
is not duplicated, and auto-linked rows are skipped so the command can be run
again safely.

    python manage.py propagate_framework_mappings --dry-run
    python manage.py propagate_framework_mappings
"""
from django.core.management.base import BaseCommand

from controls.models import ControlFrameworkMapping

from frameworks.propagation import AUTO_PREFIX, link


class Command(BaseCommand):
    help = 'Propose cross-framework equivalents for existing control mappings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Count the mappings that would be proposed without writing.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        mappings = ControlFrameworkMapping.objects.select_related(
            'control', 'framework_control__framework'
        )

        proposed = 0
        for mapping in mappings.iterator():
            if (mapping.notes or '').startswith(AUTO_PREFIX):
                continue
            proposed += link(
                mapping.control, mapping.framework_control, write=not dry_run,
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Would propose {proposed} cross-framework mapping(s). '
                f'Re-run without --dry-run to create them.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Proposed {proposed} cross-framework mapping(s) for review.'
            ))
