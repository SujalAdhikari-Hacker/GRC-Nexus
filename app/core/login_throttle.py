"""Sign-in throttling with exponential backoff.

Failed sign-ins are counted per account **and** per client IP.  Once either
counter passes its threshold, the next attempt is refused for a short,
exponentially increasing cool-down.  This is deliberately not a permanent
lockout: after the delay expires the user may try again, and the failure count
decays with ``LOGIN_FAILURE_WINDOW``.

Keeping both counters matters: the account counter stops a targeted password
guess against one user, while the IP counter slows credential stuffing across
many usernames.  Messages are generic so the form does not reveal whether a
username exists.
"""
import logging

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .rate_limit import FailureBackoff, client_ip

logger = logging.getLogger(__name__)

# Backwards-compatible module-level aliases.  The actual values are read from
# settings when the form is instantiated, so ``override_settings`` and env
# changes take effect without reloading this module.
MAX_FAILURES = getattr(settings, 'LOGIN_MAX_FAILURES', 5)
WINDOW_SECONDS = getattr(settings, 'LOGIN_FAILURE_WINDOW', 900)
LOCK_SECONDS = getattr(settings, 'LOGIN_BACKOFF_MAX_SECONDS', 900)


def _account_backoff():
    return FailureBackoff(
        'grc:login-account',
        max_failures=getattr(settings, 'LOGIN_MAX_FAILURES', MAX_FAILURES),
        window=getattr(settings, 'LOGIN_FAILURE_WINDOW', WINDOW_SECONDS),
        base=getattr(settings, 'LOGIN_BACKOFF_BASE_SECONDS', 30),
        maximum=getattr(settings, 'LOGIN_BACKOFF_MAX_SECONDS', LOCK_SECONDS),
        multiplier=getattr(settings, 'LOGIN_BACKOFF_MULTIPLIER', 2),
    )


def _ip_backoff():
    return FailureBackoff(
        'grc:login-ip',
        max_failures=getattr(settings, 'LOGIN_IP_MAX_FAILURES', 20),
        window=getattr(settings, 'LOGIN_FAILURE_WINDOW', WINDOW_SECONDS),
        base=getattr(settings, 'LOGIN_IP_BACKOFF_BASE_SECONDS', 60),
        maximum=getattr(settings, 'LOGIN_IP_BACKOFF_MAX_SECONDS', 3600),
        multiplier=getattr(settings, 'LOGIN_BACKOFF_MULTIPLIER', 2),
    )


def _identity(username):
    return (username or '').strip().lower()[:150] or 'anonymous'


def seconds_until_unlock(username, ip):
    """Seconds until the account or IP may try again; ``None`` when clear."""
    account = _account_backoff().retry_after(_identity(username))
    address = _ip_backoff().retry_after(ip or 'unknown')
    remaining = max(account, address)
    return remaining or None


def register_failure(username, ip):
    """Count a failed attempt against both the account and the client IP."""
    account_failures = _account_backoff().register_failure(_identity(username))
    ip_failures = _ip_backoff().register_failure(ip or 'unknown')
    logger.warning(
        'Failed sign-in for %r from %s (account failures=%d, ip failures=%d)',
        username, ip, account_failures, ip_failures,
    )
    return account_failures, ip_failures


def clear_failures(username, ip):
    """Successful sign-in clears the account counter.

    The IP counter is intentionally left to decay.  Clearing it here would let
    an attacker with one valid account reset the credential-stuffing counter
    for the whole address.
    """
    _account_backoff().clear(_identity(username))


def clear_ip_failures(ip):
    """Administrative/test helper for resetting an address counter."""
    _ip_backoff().clear(ip or 'unknown')


class ThrottledAuthenticationForm(AuthenticationForm):
    """AuthenticationForm that enforces exponential backoff before auth."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # AuthenticationForm's password field has no upper bound.  Cap it so a
        # multi-megabyte password cannot be used as a cheap CPU/memory probe.
        self.fields['password'].max_length = getattr(
            settings, 'LOGIN_PASSWORD_MAX_LENGTH', 4096
        )
        self.fields['username'].max_length = getattr(
            settings, 'LOGIN_USERNAME_MAX_LENGTH', 150
        )

    def clean(self):
        username = self.cleaned_data.get('username') or ''
        request = getattr(self, 'request', None)
        ip = client_ip(request) if request is not None else 'unknown'

        remaining = seconds_until_unlock(username, ip)
        if remaining:
            minutes = max(1, (remaining + 59) // 60)
            raise ValidationError(
                'Too many failed sign-in attempts. '
                f'Try again in about {minutes} minute(s).',
                code='throttled',
            )

        try:
            return super().clean()
        except ValidationError:
            register_failure(username, ip)
            raise
