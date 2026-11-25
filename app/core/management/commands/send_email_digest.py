"""Email each opted-in user a digest of what is outstanding for them.

Typical schedule: daily in the morning, e.g.::

    docker compose exec -T web python manage.py send_email_digest

Each user controls this from Account -> Settings (Off / Daily / Weekly). The
command respects that window, so a daily run will not mail someone who chose
"weekly" more than once a week.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.utils import timezone

from core.emails import email_pref_allows, send_digest_email
from core.management.base import LoggedCommand
from core.notification_registry import refresh_notifications
from core.notifications import Notification
from core.settings_model import UserPreference

# Escalation kinds count as "overdue" in the digest headline.
_OVERDUE_KINDS = {
    'risk_escalated', 'risk_overdue', 'finding_overdue', 'action_overdue',
    'ticket_overdue', 'exception_expiring', 'vendor_contract_expired',
    'vuln_sla_breach',
}

_MAX_ITEMS = 25


def _interval_for(frequency):
    if frequency == 'weekly':
        return timedelta(days=6)
    return timedelta(hours=20)  # daily — a little under 24h so a fixed cron lands


def _is_due(pref, now, force):
    """Is this user due a digest?

    ``--force`` bypasses the *time window* only — it never overrides an explicit
    ``off``. Turning digests off is a consent decision, not a schedule one.
    """
    if pref is not None:
        frequency = getattr(pref, 'email_digest_frequency', 'weekly')
        if frequency == 'off':
            return False
    if force or pref is None:
        return True
    last = getattr(pref, 'last_digest_sent_at', None)
    if last is None:
        return True
    return (now - last) >= _interval_for(frequency)


def _digest_items(user):
    """Unread, unresolved notifications visible to ``user``."""
    query = Notification.objects.filter(is_read=False, is_cleared=False)
    if not user.is_superuser:
        from django.db.models import Q
        condition = Q(recipient=user)
        if user.department_id:
            condition |= Q(owner_dept_id=user.department_id)
        query = query.filter(condition)

    notes = list(query.order_by('-created_at')[:_MAX_ITEMS])
    items = [
        {
            'title': note.title,
            'meta': note.get_kind_display(),
            'url': note.action_url or '/notifications/',
            'severity': 'danger' if note.kind in _OVERDUE_KINDS else 'warning',
        }
        for note in notes
    ]
    overdue = sum(1 for note in notes if note.kind in _OVERDUE_KINDS)
    return items, overdue


class Command(LoggedCommand):
    help = 'Email opted-in users a digest of their outstanding notifications.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Send regardless of the frequency window.')
        parser.add_argument('--user', help='Only this username.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show who would receive a digest.')

    def handle(self, *args, **options):
        User = get_user_model()
        now = timezone.now()

        # Clear anything already resolved so the digest is honest.
        refresh_notifications(is_super=True)

        users = (
            User.objects.filter(is_active=True)
            .exclude(email='')
            .select_related('preference')
            .order_by('username')
        )
        if options['user']:
            users = users.filter(username=options['user'])
            if not users.exists():
                raise CommandError(f"No active user named {options['user']!r}.")

        sent = 0
        skipped_window = 0
        skipped_empty = 0
        skipped_optout = 0

        for user in users:
            pref = getattr(user, 'preference', None)
            if not email_pref_allows(user):
                skipped_optout += 1
                continue
            if not _is_due(pref, now, options['force']):
                skipped_window += 1
                continue

            items, overdue = _digest_items(user)
            if not items:
                skipped_empty += 1
                continue

            if options['dry_run']:
                self.stdout.write(
                    f"  would email {user.username} <{user.email}> — "
                    f"{len(items)} item(s), {overdue} overdue"
                )
                sent += 1
                continue

            delivered = send_digest_email(
                user, items, overdue_count=overdue,
                subject_label=(
                    'Weekly digest'
                    if getattr(pref, 'email_digest_frequency', 'weekly') == 'weekly'
                    else 'Daily digest'
                ),
            )
            if delivered:
                # Create the preference row if the user never opened Settings —
                # otherwise there is nowhere to stamp the window and an hourly
                # cron would mail them every single run.
                pref = UserPreference.get_for(user)
                pref.last_digest_sent_at = now
                pref.save(update_fields=['last_digest_sent_at'])
                sent += 1
                self.stdout.write(f"  emailed {user.username} ({len(items)} items)")

        verb = 'would send' if options['dry_run'] else 'sent'
        self.record_counts(
            sent=sent,
            skipped_window=skipped_window,
            skipped_empty=skipped_empty,
            skipped_optout=skipped_optout,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Digest complete — {verb} {sent}; "
            f"skipped: {skipped_window} outside window, "
            f"{skipped_empty} nothing to report, "
            f"{skipped_optout} opted out."
        ))
