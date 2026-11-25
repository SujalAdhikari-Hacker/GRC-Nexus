from core.management.base import LoggedCommand

from tickets.alerts import scan_and_create_tickets


class Command(LoggedCommand):
    help = 'Scan the system for alert conditions and auto-create tickets.'

    def add_arguments(self, parser):
        parser.add_argument('--quiet', action='store_true', help='Suppress per-event output')

    def handle(self, *args, **options):
        verbose = not options['quiet']
        self.stdout.write(self.style.MIGRATE_HEADING('Scanning for alerts...\n'))

        results = scan_and_create_tickets(verbose=verbose)

        total_created = sum(r.get('tickets_created', 0) for r in results.values())
        total_events = sum(r.get('events_found', 0) for r in results.values())

        self.stdout.write('\n' + self.style.MIGRATE_HEADING('Summary:'))
        for rule_name, r in results.items():
            if 'error' in r:
                self.stdout.write(f'  {rule_name:<35} ERROR: {r["error"][:70]}')
            else:
                self.stdout.write(
                    f'  {rule_name:<35} {r["tickets_created"]:>3} created / {r["events_found"]:>3} events'
                )

        self.stdout.write('')
        self.record_counts(tickets_created=total_created, events_found=total_events)
        self.stdout.write(self.style.SUCCESS(
            f'Scan complete. {total_created} ticket(s) created from {total_events} alert event(s).'
        ))