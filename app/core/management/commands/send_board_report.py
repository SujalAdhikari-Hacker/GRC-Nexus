"""Generate and email the scheduled monthly executive PDF board-report pack.

Designed to run monthly via cron (safe to run daily as well because the 27-day
cooldown window prevents duplicate monthly sends unless ``--force`` is given):

    docker compose exec -T web python manage.py send_board_report
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.utils import timezone

from core.emails import email_for, email_pref_allows, send_board_report_email
from core.executive_report import build_executive_report
from core.management.base import LoggedCommand
from core.models import OrganisationProfile
from core.reports import render_pdf_bytes

MONTHLY_COOLDOWN_DAYS = 27


def _is_monthly_due(org, now, force):
    if force:
        return True
    last = getattr(org, 'last_board_report_sent_at', None)
    if last is None:
        return True
    return (now - last) >= timedelta(days=MONTHLY_COOLDOWN_DAYS)


def _split_addresses(raw):
    if not raw:
        return []
    return [addr.strip() for addr in re.split(r'[,;\n\r]+', str(raw)) if addr.strip()]


def resolve_board_recipients(org, explicit_to=None):
    """Resolve deduplicated board report recipient addresses."""
    if explicit_to:
        candidates = []
        for entry in explicit_to:
            candidates.extend(_split_addresses(entry))
        return list(dict.fromkeys(candidates))

    candidates = []
    for user_obj in (org.executive_sponsor, org.security_committee_chair):
        if user_obj and getattr(user_obj, 'is_active', False):
            addr = email_for(user_obj)
            if addr:
                candidates.append(addr)

    candidates.extend(_split_addresses(org.board_report_recipients))
    candidates.extend(
        a.strip() for a in getattr(settings, 'BOARD_REPORT_RECIPIENTS', []) if a.strip()
    )

    addresses = list(dict.fromkeys(candidates))
    if addresses:
        return addresses

    # Fallback: opted-in active superusers with email addresses.
    User = get_user_model()
    fallback = []
    for su in User.objects.filter(is_active=True, is_superuser=True).select_related('preference').order_by('pk'):
        if email_pref_allows(su):
            fallback.append(email_for(su))
    return list(dict.fromkeys(fallback))


class Command(LoggedCommand):
    help = 'Generate the monthly executive PDF report and email it to board recipients.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Send regardless of enabled switch or monthly window.')
        parser.add_argument('--to', nargs='*',
                            help='Explicit recipient email address(es) to override defaults.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Render report and show recipients without emailing.')

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        force = bool(options.get('force'))
        dry_run = bool(options.get('dry_run'))
        org = OrganisationProfile.get()

        if not org.board_report_enabled and not force:
            self.record_counts(sent=0, skipped_disabled=1, skipped_window=0, skipped_no_recipients=0)
            self.stdout.write('Board report pack is disabled in Organisation Profile.')
            return

        if not _is_monthly_due(org, now, force):
            self.record_counts(sent=0, skipped_disabled=0, skipped_window=1, skipped_no_recipients=0)
            self.stdout.write('Monthly board report already sent within the current cycle.')
            return

        recipients = resolve_board_recipients(org, options.get('to'))
        if not recipients:
            self.record_counts(sent=0, skipped_disabled=0, skipped_window=0, skipped_no_recipients=1)
            self.stdout.write(self.style.WARNING('No board report recipients configured.'))
            return

        User = get_user_model()
        report_user = User.objects.filter(is_active=True, is_superuser=True).order_by('pk').first()
        if report_user is None:
            raise CommandError('No active superuser available to generate the org-wide board report.')

        report_data = build_executive_report(report_user)
        pdf_bytes = render_pdf_bytes(
            'reports/executive_report.html',
            report_data,
            generated_by=report_user,
        )
        period_label = today.strftime('%B %Y')
        filename = f'grcnexus_board_report_{today:%Y-%m}.pdf'

        if dry_run:
            self.stdout.write(
                f'Would email {filename} ({len(pdf_bytes)} bytes) to: {", ".join(recipients)}'
            )
            return

        delivered = send_board_report_email(
            recipients,
            pdf_bytes,
            report_data=report_data,
            period_label=period_label,
            filename=filename,
        )
        if delivered:
            org.last_board_report_date = today
            org.last_board_report_sent_at = now
            org.save(update_fields=['last_board_report_date', 'last_board_report_sent_at'])

        self.record_counts(
            sent=delivered,
            recipients=len(recipients),
            pdf_bytes=len(pdf_bytes),
            skipped_disabled=0,
            skipped_window=0,
            skipped_no_recipients=0,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Board report pack complete — delivered={delivered} to {len(recipients)} recipient(s) ({filename}).'
        ))
