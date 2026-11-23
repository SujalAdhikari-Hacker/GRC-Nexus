"""Runtime email configuration and notification delivery.

The SMTP settings live in the database (``core.EmailSettings``) so an
administrator can configure delivery from the UI without editing ``.env`` or
restarting the container. When SMTP is disabled the project keeps the previous
behaviour: ``settings.EMAIL_BACKEND`` (console by default) writes messages to
the server log.
"""
import logging

from django.conf import settings
from django.core.mail import get_connection

logger = logging.getLogger(__name__)

# Notifications worth an immediate email. Routine "this record needs an owner"
# housekeeping stays in-app (and in the digest) so creating an asset does not
# send three separate messages.
IMMEDIATE_KINDS = {
    'risk_escalated',
    'risk_overdue',
    'finding_overdue',
    'action_overdue',
    'ticket_overdue',
    'exception_expiring',
    'exception_approval_needed',
    'vendor_contract_expired',
    'kri_red',
    'vuln_sla_breach',
    'incident_open',
    'incident_sla_breach',
    'incident_breach_due',
    'incident_nis2_due',
    'incident_nis2_breach',
    'policy_needs_approval',
}


def get_email_settings():
    """The singleton row, or ``None`` before migrations have run."""
    try:
        from .settings_model import EmailSettings
        return EmailSettings.get_solo()
    except Exception:  # database not ready, or table missing during migrate
        logger.debug('Email settings are not available yet', exc_info=True)
        return None


def smtp_is_configured():
    cfg = get_email_settings()
    return bool(cfg and cfg.is_enabled and cfg.host)


def build_connection(fail_silently=False):
    """Return a Django email backend for the current configuration."""
    cfg = get_email_settings()
    if cfg and cfg.is_enabled and cfg.host:
        return get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=cfg.host,
            port=cfg.port,
            username=cfg.username or '',
            password=cfg.password,
            use_tls=cfg.use_tls,
            use_ssl=cfg.use_ssl,
            timeout=cfg.timeout,
            fail_silently=fail_silently,
        )
    return get_connection(
        backend=settings.EMAIL_BACKEND, fail_silently=fail_silently,
    )


def from_header():
    """The From: value for outbound mail."""
    cfg = get_email_settings()
    if cfg and cfg.is_enabled and cfg.from_email:
        return cfg.from_header
    return settings.DEFAULT_FROM_EMAIL


def describe():
    """Human-readable current delivery mode, shown in the settings UI."""
    cfg = get_email_settings()
    if cfg and cfg.is_enabled and cfg.host:
        return f'SMTP {cfg.host}:{cfg.port} ({cfg.get_security_display()})'
    backend = settings.EMAIL_BACKEND
    if backend.endswith('console.EmailBackend'):
        return 'Console backend — messages are written to the server log'
    return f'Fallback backend: {backend}'


def _pref_flag(kind):
    if kind.startswith('ticket_'):
        return 'email_on_ticket_assigned'
    if kind.startswith('risk_'):
        return 'email_on_risk_breach'
    if kind.startswith(('finding_', 'action_', 'audit_')):
        return 'email_on_audit_finding'
    if kind.startswith('kri_'):
        return 'email_on_kri_red'
    if kind.startswith('vuln_'):
        return 'email_on_vuln_sla'
    if kind.startswith('incident_'):
        return 'email_on_incident'
    return 'email_on_escalation'


def _recipients(notification):
    """Targeted user, else the department HOD(s), else superusers."""
    from core.models import User

    if notification.recipient_id and notification.recipient:
        return [notification.recipient]
    if notification.owner_dept_id:
        hods = list(User.objects.filter(
            department_id=notification.owner_dept_id,
            is_hod=True,
            is_active=True,
        ))
        if hods:
            return hods
    return list(User.objects.filter(is_superuser=True, is_active=True))


def send_notification_email(notification):
    """Email the people responsible for a high-signal notification.

    Returns the number delivered. Never raises: a broken relay must not break
    the save that created the notification.
    """
    cfg = get_email_settings()
    if not cfg or not cfg.is_enabled or not cfg.notify_on_new:
        return 0
    if notification.kind not in IMMEDIATE_KINDS:
        return 0

    from .emails import (
        email_for, email_pref_allows, render_html, render_text, send_email,
    )

    flag = _pref_flag(notification.kind)
    users = [u for u in _recipients(notification) if email_pref_allows(u, flag)]
    addresses = list(dict.fromkeys(
        email_for(u) for u in users if email_for(u)
    ))
    if not addresses:
        return 0

    heading = notification.title
    intro = 'A notification in GRC Nexus needs your attention.'
    items = [{
        'title': notification.title,
        'meta': notification.get_kind_display(),
        'url': notification.action_url or '/notifications/',
        'severity': 'danger' if notification.kind.startswith(('risk_', 'incident_'))
        else 'warning',
    }]
    subject = f'[GRC Nexus] {notification.title}'
    try:
        return send_email(
            subject,
            render_text(heading, intro, items, cta_url='/notifications/',
                        cta_label='Open GRC Nexus'),
            addresses,
            html_body=render_html(heading, intro, items, cta_url='/notifications/',
                                  cta_label='View notification'),
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception('Notification email failed for %s', notification.pk)
        return 0


def schedule_notification_email(notification):
    """Send after the surrounding transaction commits."""
    from django.db import transaction

    def _send():
        try:
            send_notification_email(notification)
        except Exception:  # pragma: no cover - defensive
            logger.exception('Deferred notification email failed')

    transaction.on_commit(_send)


def send_announcement_email(notification):
    """Email one announcement to everyone who can see it.

    Unlike automatic notifications this is opt-in per message, so the
    ``notify_on_new`` master switch is not consulted — only whether SMTP is
    enabled and whether each person still wants email at all.
    """
    cfg = get_email_settings()
    if not cfg or not cfg.is_enabled or not cfg.host:
        return 0

    from .announcements import recipients_for
    from .emails import (
        email_for, email_pref_allows, render_html, render_text, send_email,
    )
    from django.utils.html import escape

    users = [u for u in recipients_for(notification) if email_pref_allows(u)]
    addresses = list(dict.fromkeys(
        email_for(u) for u in users if email_for(u)
    ))
    if not addresses:
        return 0

    sender = notification.sent_by
    sender_name = (
        (sender.get_full_name() or sender.username) if sender else 'GRC Nexus'
    )
    body = notification.body or 'You have a new message in GRC Nexus.'
    items = [{
        'title': notification.title,
        'meta': f'From {sender_name}',
        'url': '/notifications/',
        'severity': 'info',
    }]
    try:
        return send_email(
            f'[GRC Nexus] {notification.title}',
            render_text(
                notification.title, body, items,
                cta_url='/notifications/', cta_label='Open GRC Nexus',
            ),
            addresses,
            html_body=render_html(
                notification.title,
                escape(body).replace('\n', '<br>'),
                items,
                cta_url='/notifications/',
                cta_label='View notification',
            ),
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception('Announcement email failed for %s', notification.pk)
        return 0


def schedule_announcement_email(notification):
    """Send an announcement email after the surrounding transaction commits."""
    from django.db import transaction

    def _send():
        try:
            send_announcement_email(notification)
        except Exception:  # pragma: no cover - defensive
            logger.exception('Deferred announcement email failed')

    transaction.on_commit(_send)


def send_test_message(recipient):
    """Send a sample message through the current configuration."""
    from .emails import render_html, render_text, send_email

    heading = 'SMTP test message'
    intro = (
        'If you can read this, GRC Nexus can deliver email through your '
        'configured SMTP server.'
    )
    items = [{
        'title': 'Delivery confirmed',
        'meta': f'Sent to {recipient}',
        'url': '/settings/email/',
        'severity': 'info',
    }]
    return send_email(
        '[GRC Nexus] SMTP test message',
        render_text(heading, intro, items),
        [recipient],
        html_body=render_html(heading, intro, items),
    )
