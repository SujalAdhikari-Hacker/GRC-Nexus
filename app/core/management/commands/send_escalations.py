"""Scan for overdue / escalating items, raise notifications and email owners.

Intended to run on a schedule (hourly or daily), e.g.::

    docker compose exec -T web python manage.py send_escalations

It is safe to run as often as you like — an item is only emailed once while it
remains unresolved.
"""
from core.escalations import run_escalations
from core.management.base import LoggedCommand


class Command(LoggedCommand):
    help = (
        'Find overdue tasks, breached tolerances, expiring exceptions and '
        'lapsed vendor contracts; notify the responsible people in-app and by '
        'email.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would escalate without writing anything.',
        )
        parser.add_argument(
            '--no-email', action='store_true',
            help='Raise in-app notifications but send no email.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        summary = run_escalations(
            dry_run=dry_run,
            send_emails=not options['no_email'],
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing written.'))
            self.stdout.write('')
            for item in summary['items']:
                self.stdout.write(f"  · {item['title']}")
                if item['meta']:
                    self.stdout.write(f"      {item['meta']}")
            self.stdout.write('')
            self.stdout.write(f"{summary['found']} item(s) would escalate.")
            return

        self.stdout.write(
            f"Scanned {summary['found']} escalating item(s); "
            f"{summary['created']} newly notified; "
            f"{summary['emailed']} item(s) emailed to "
            f"{summary['recipients']} recipient(s)."
        )
        self.record_counts(
            found=summary['found'],
            created=summary['created'],
            emailed=summary['emailed'],
            recipients=summary['recipients'],
        )
        if (
            not options['no_email']
            and summary['created']
            and not summary['recipients']
        ):
            self.stdout.write(self.style.WARNING(
                'No emails were sent — every affected user has email '
                'notifications disabled or no address. Set '
                'ESCALATION_FALLBACK_EMAILS to catch these.'
            ))
        self.stdout.write(self.style.SUCCESS('Escalation scan complete.'))
