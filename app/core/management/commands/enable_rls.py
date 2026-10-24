"""Install or remove the PostgreSQL row-level-security policies."""
from django.core.management.base import BaseCommand
from django.db import connection

from core.rls import apply_rls, remove_rls


class Command(BaseCommand):
    help = 'Install/refresh (or remove) PostgreSQL department row-level security.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--disable', action='store_true',
            help='Remove the policies and disable RLS on the scoped tables.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print the SQL without executing it.',
        )

    def handle(self, *args, **options):
        if options['disable']:
            remove_rls(connection=connection)
            self.stdout.write(self.style.SUCCESS('RLS policies removed.'))
            return

        statements = apply_rls(
            connection=connection, dry_run=options['dry_run']
        )
        if options['dry_run']:
            for statement in statements:
                self.stdout.write(statement.strip() + ';')
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run: {len(statements)} statement(s) not executed.'
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f'RLS installed/refreshed ({len(statements)} statements).'
            )
        )
