"""Sign-in throttling.

Brute-force protection for the stock :class:`django.contrib.auth.views.LoginView`
without new dependencies: failed attempts are counted in the default cache,
keyed by ``(client IP, username)``. After
``settings.LOGIN_MAX_FAILURES`` (default 5) failures inside
``LOGIN_FAILURE_WINDOW`` (default 15 minutes), further sign-in attempts for
that identity are refused for ``LOGIN_LOCKOUT_SECONDS`` (default 15 minutes) —
before the password is even checked, so locked accounts give no
valid/invalid-password feedback.

The default cache is per-process (locmem). With a single WSGI process —
the deployment shape for this product — that is a real barrier; multi-worker
deployments should point the cache at a shared backend (Redis) to make the
lockout global. ``django-axes`` remains a drop-in stronger option and is
deliberately not a dependency: everything here degrades gracefully (a cache
miss never locks a legitimate user out).
"""
import logging

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_FAILURES = getattr(settings, 'LOGIN_MAX_FAILURES', 5)
WINDOW_SECONDS = getattr(settings, 'LOGIN_FAILURE_WINDOW', 15 * 60)
LOCK_SECONDS = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 15 * 60)


def _keys(username, ip):
    ident = f'{ip or "unknown"}|{(username or "").strip().lower()[:100]}'
    return f'grc:login-fails:{ident}', f'grc:login-lock:{ident}'


def seconds_until_unlock(username, ip):
    """Seconds until the identity may sign in again; ``None`` when not locked."""
    _, lock_key = _keys(username, ip)
    until = cache.get(lock_key)
    if until is None:
        return None
    return max(0, int((until - timezone.now()).total_seconds()))


def register_failure(username, ip):
    """Count a failed attempt; engage the lockout at ``MAX_FAILURES``."""
    fails_key, lock_key = _keys(username, ip)
    fails = (cache.get(fails_key) or 0) + 1
    if fails >= MAX_FAILURES:
        cache.set(lock_key, timezone.now() + timezone.timedelta(seconds=LOCK_SECONDS), LOCK_SECONDS)
        cache.delete(fails_key)
        logger.warning(
            'Sign-in lockout engaged for %r from %s (%d failures)',
            username, ip, fails,
        )
    else:
        cache.set(fails_key, fails, WINDOW_SECONDS)
    return fails


def clear_failures(username, ip):
    """Successful sign-in resets the counter for the identity."""
    fails_key, lock_key = _keys(username, ip)
    cache.delete(fails_key)
    cache.delete(lock_key)


class ThrottledAuthenticationForm(AuthenticationForm):
    """AuthenticationForm that enforces the lockout before authenticating."""

    def clean(self):
        username = self.cleaned_data.get('username') or ''
        request = getattr(self, 'request', None)
        ip = request.META.get('REMOTE_ADDR', '') if request is not None else ''

        remaining = seconds_until_unlock(username, ip)
        if remaining:
            minutes = max(1, remaining // 60)
            raise ValidationError(
                'Too many failed sign-in attempts. '
                f'Try again in about {minutes} minute(s).',
                code='locked_out',
            )

        try:
            return super().clean()
        except ValidationError:
            register_failure(username, ip)
            raise
