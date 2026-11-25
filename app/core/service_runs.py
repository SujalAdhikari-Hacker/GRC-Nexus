"""Durable history for the scheduled management commands.

Every cron-worthy command wraps its work in :func:`record_run`, which writes a
``ServiceRun`` row when the command starts and closes it when the command
finishes or blows up. ``LoggedCommand`` does the wrapping for you; a command
only has to subclass it and report its numbers with ``self.record_counts(...)``.

Dry runs are not recorded: they are interactive, change nothing, and would
otherwise bury the real runs.
"""
from contextlib import contextmanager

from django.utils import timezone

from .models import ServiceRun

# Operational history, not audit evidence: a year of hourly rows is plenty and
# the table should not grow without bound on a box nobody prunes.
RETENTION_DAYS = 90


def _describe(exc):
    text = str(exc).strip()
    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__


def _prune():
    cutoff = timezone.now() - timezone.timedelta(days=RETENTION_DAYS)
    ServiceRun.objects.filter(started_at__lt=cutoff).delete()


@contextmanager
def record_run(service):
    """Record one run of ``service``; failures are recorded and re-raised."""
    run = ServiceRun.objects.create(service=service)
    try:
        yield run
    except BaseException as exc:
        run.finish('failed', _describe(exc))
        raise
    else:
        run.finish('ok')
    finally:
        _prune()
