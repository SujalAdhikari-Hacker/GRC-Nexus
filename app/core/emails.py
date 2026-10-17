"""Outbound email for GRC Nexus — digests and escalation notifications.

Design rules:

* **Sending never raises.** A broken SMTP relay must not roll back a save, kill
  a scheduled scan, or 500 a page. Failures are logged and return ``0``.
* **Preferences are honoured centrally.** :func:`email_pref_allows` is the one
  place that decides whether a user wants a given class of mail, so the
  commands and views stay thin.
* **Links are absolute.** Scheduled jobs have no request, so every link is
  built from ``settings.SITE_BASE_URL``.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)

# Neutral, light, email-client-safe palette. HTML email cannot rely on
# brand.css or CSS variables, so colours are inlined here on purpose.
_BRAND = '#0B1220'
_MUTED = '#64748B'
_BORDER = '#E5E7EB'
_DANGER = '#DC2626'
_WARNING = '#D97706'
_BG = '#F1F5F9'

_SEVERITY_COLOUR = {
    'danger': _DANGER,
    'warning': _WARNING,
    'info': _MUTED,
}


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

def site_url(path=''):
    """Absolute URL for ``path`` on this deployment."""
    base = (getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')
    if not path:
        return base or '/'
    if str(path).startswith(('http://', 'https://')):
        return str(path)
    return f'{base}/{str(path).lstrip("/")}'


# ---------------------------------------------------------------------------
# Preference + address resolution
# ---------------------------------------------------------------------------

def email_for(user):
    """The address to mail ``user`` at, or '' when there is none."""
    if not user:
        return ''
    return (getattr(user, 'email', '') or '').strip()


def email_pref_allows(user, flag=None):
    """True when ``user`` should receive mail.

    ``flag`` is an attribute name on ``UserPreference`` (e.g.
    ``'email_on_risk_breach'``). When the user has no preference row we treat
    mail as allowed — the master switch defaults on.
    """
    if not user or not getattr(user, 'is_active', False):
        return False
    if not email_for(user):
        return False

    pref = getattr(user, 'preference', None)
    if pref is None:
        return True
    if not getattr(pref, 'email_notifications_enabled', True):
        return False
    if flag and not getattr(pref, flag, True):
        return False
    return True


def _unique_addresses(users):
    """De-duplicated, non-empty addresses for an iterable of users."""
    seen = []
    for user in users:
        address = email_for(user)
        if address and address not in seen:
            seen.append(address)
    return seen


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def send_email(subject, text_body, recipients, *, html_body=None):
    """Send one message to many recipients. Returns the number delivered.

    Never raises: any transport error is logged and reported as ``0``.
    """
    recipients = list(dict.fromkeys([r for r in (recipients or []) if r]))
    if not recipients:
        return 0

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        if html_body:
            message.attach_alternative(html_body, 'text/html')
        return message.send(fail_silently=False)
    except Exception:  # pragma: no cover - depends on the SMTP transport
        logger.exception('Failed to send %r to %s', subject, recipients)
        return 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _items_html(items):
    rows = []
    for item in items:
        colour = _SEVERITY_COLOUR.get(item.get('severity', 'info'), _MUTED)
        title = escape(item.get('title', ''))
        meta = escape(item.get('meta', ''))
        url = item.get('url')
        if url:
            title = (
                f'<a href="{escape(site_url(url))}" '
                f'style="color:{_BRAND};text-decoration:none;">{title}</a>'
            )
        rows.append(
            '<tr>'
            f'<td style="width:4px;background:{colour};"></td>'
            '<td style="padding:10px 14px;border-bottom:1px solid '
            f'{_BORDER};font-size:14px;color:{_BRAND};">'
            f'<div style="font-weight:600;">{title}</div>'
            f'<div style="color:{_MUTED};font-size:12.5px;padding-top:2px;">'
            f'{meta}</div>'
            '</td>'
            '</tr>'
        )
    return ''.join(rows)


def render_html(heading, intro, items, *, cta_url=None, cta_label=None,
                footer=None):
    """A minimal, table-based HTML body that survives most mail clients."""
    rows = _items_html(items)
    cta = ''
    if cta_url and cta_label:
        cta = (
            '<div style="padding:18px 20px;">'
            f'<a href="{escape(site_url(cta_url))}" '
            f'style="background:{_BRAND};color:#fff;padding:10px 18px;'
            'border-radius:6px;text-decoration:none;font-size:14px;'
            f'font-weight:600;">{escape(cta_label)}</a>'
            '</div>'
        )
    footer_html = footer or (
        'You are receiving this because email notifications are enabled on your '
        'GRC Nexus account. Manage them under Account &rarr; Settings.'
    )
    return f"""\
<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:{_BG};
 font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="background:{_BG};padding:24px 12px;">
  <tr><td align="center">
   <table role="presentation" width="600" cellpadding="0" cellspacing="0"
    style="max-width:600px;background:#fff;border:1px solid {_BORDER};
     border-radius:10px;overflow:hidden;">
    <tr><td style="padding:18px 20px;border-bottom:1px solid {_BORDER};">
      <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;
       color:{_MUTED};">GRC Nexus</div>
      <div style="font-size:19px;font-weight:700;color:{_BRAND};
       padding-top:4px;">{escape(heading)}</div>
    </td></tr>
    <tr><td style="padding:16px 20px 4px;font-size:14px;color:{_BRAND};">
      {intro}
    </td></tr>
    <tr><td><table role="presentation" width="100%" cellpadding="0"
      cellspacing="0">{rows}</table></td></tr>
    {cta}
    <tr><td style="padding:14px 20px;background:{_BG};color:{_MUTED};
      font-size:12px;border-top:1px solid {_BORDER};">
      {footer_html}
    </td></tr>
   </table>
  </td></tr>
 </table>
</body></html>"""


def render_text(heading, intro, items, *, cta_url=None, cta_label=None):
    lines = [heading, '=' * len(heading), '', intro, '']
    for item in items:
        lines.append(f"- {item.get('title', '')}")
        meta = item.get('meta')
        if meta:
            lines.append(f"    {meta}")
        if item.get('url'):
            lines.append(f"    {site_url(item['url'])}")
        lines.append('')
    if cta_url and cta_label:
        lines += [f"{cta_label}: {site_url(cta_url)}", '']
    lines.append('— GRC Nexus')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# The two things the commands actually send
# ---------------------------------------------------------------------------

def send_digest_email(user, items, *, overdue_count=0, window_label='today',
                      subject_label='Digest'):
    """Send ``user`` a summary of their outstanding notifications."""
    if not items:
        return 0

    heading = f'Your GRC Nexus digest — {len(items)} item(s) need attention'
    intro_bits = [f'Here is what is waiting for you {window_label}.']
    if overdue_count:
        intro_bits.append(
            f'<strong style="color:{_DANGER};">{overdue_count} item(s) are '
            'overdue.</strong>'
        )
    intro = ' '.join(intro_bits)

    subject = f'[GRC Nexus] {subject_label} — {len(items)} open item(s)'
    return send_email(
        subject,
        render_text(heading, intro, items, cta_url='/notifications/',
                    cta_label='Open GRC Nexus'),
        [email_for(user)],
        html_body=render_html(heading, intro, items, cta_url='/notifications/',
                              cta_label='View all notifications'),
    )


def send_escalation_email(recipients, items, *, dept_name=None):
    """Send an escalation alert to ``recipients`` (User objects or addresses)."""
    if not items:
        return 0

    addresses = []
    for recipient in recipients:
        if isinstance(recipient, str):
            addresses.append(recipient)
        else:
            addresses.extend(_unique_addresses([recipient]))
    addresses = list(dict.fromkeys(addresses))
    if not addresses:
        return 0

    scope = f' — {dept_name}' if dept_name else ''
    heading = f'Escalation{scope}: {len(items)} item(s) past tolerance'
    intro = (
        'The items below have breached a due date or tolerance threshold and '
        'need action.'
    )
    subject = f'[GRC Nexus] Escalation — {len(items)} item(s) need action'

    return send_email(
        subject,
        render_text(heading, intro, items, cta_url='/notifications/',
                    cta_label='Open GRC Nexus'),
        addresses,
        html_body=render_html(heading, intro, items, cta_url='/notifications/',
                              cta_label='Open GRC Nexus'),
    )
