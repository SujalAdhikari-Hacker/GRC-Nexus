"""Base class for management commands that must leave a trace.

See :mod:`core.service_runs`. Any command that runs unattended (cron, sidecar)
should subclass :class:`LoggedCommand` instead of ``BaseCommand`` so the
service-run page can show that it ran, whether it worked and what it counted.
"""
from django.core.management.base import BaseCommand

from core.service_runs import record_run


class LoggedCommand(BaseCommand):
    """Record one ``ServiceRun`` per invocation, keyed by the command name."""

    run = None

    def execute(self, *args, **options):
        # Dry runs are interactive and write nothing; logging them would make
        # the real history harder to read.
        if options.get('dry_run'):
            return super().execute(*args, **options)
        with record_run(self._service_name()) as run:
            self.run = run
            return super().execute(*args, **options)

    def record_counts(self, **counts):
        """Attach integer counts to this run; ignored when nothing is recorded."""
        if self.run is not None:
            self.run.counts = {**self.run.counts, **counts}

    def _service_name(self):
        # 'core.management.commands.send_escalations' -> 'send_escalations'
        return self.__class__.__module__.rsplit('.', 1)[-1]
