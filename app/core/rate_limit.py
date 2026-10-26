"""Configurable request throttling and exponential failure backoff.

Two layers share this module:

* :class:`RateLimit` / :func:`check_request_limit` implement the request-rate
  buckets used by :class:`core.middleware.RateLimitMiddleware`.  Authentication
  routes use an exponential cool-down; ordinary read/write buckets use a plain
  fixed window.
* :class:`FailureBackoff` counts failed authentication attempts.  It never
  permanently locks an account: each failure past the configured threshold
  increases the wait before the next attempt, up to a configurable ceiling.

All thresholds are settings/env values, so operators can tune them without a
code change.  The default cache is per-process; a multi-worker deployment must
point ``CACHES`` at Redis for the counters to be shared.
"""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def client_ip(request):
    """Return the client address, honouring a trusted proxy chain.

    ``X-Forwarded-For`` is only read when ``TRUSTED_PROXY_HOPS`` is greater than
    zero, and only the address added by our own proxy chain is used. A client
    cannot rotate the header to escape a rate limit unless it can reach the app
    without passing through those proxies.
    """
    remote = (request.META.get('REMOTE_ADDR') or 'unknown')[:64]
    hops = _setting('TRUSTED_PROXY_HOPS', 0)
    try:
        hops = int(hops)
    except (TypeError, ValueError):
        hops = 0
    if hops <= 0:
        return remote

    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    parts = [part.strip() for part in forwarded.split(',') if part.strip()]
    if len(parts) < hops:
        return remote

    candidate = _normalise_ip(parts[-hops])
    return candidate or remote


def _normalise_ip(value):
    """Return a canonical IP string, or None when the value is not an IP."""
    value = (value or '').strip()
    if not value:
        return None
    if value.startswith('['):  # [2001:db8::1]:443
        value = value[1:value.find(']')] if ']' in value else value[1:]
    elif value.count(':') == 1:  # 203.0.113.5:443
        value = value.split(':', 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_identity(request):
    """Key a rate-limit bucket by user when signed in, otherwise by IP."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return f'user:{user.pk}'
    return f'ip:{client_ip(request)}'


def _setting(name, default):
    return getattr(settings, name, default)


@dataclass(frozen=True)
class RateLimit:
    """One request bucket."""

    bucket: str
    limit: int
    window: int
    backoff: bool = False
    backoff_base: int = 30
    backoff_max: int = 900
    backoff_multiplier: int = 2


# Auth paths are deliberately narrow: only the sign-in, password-change and
# second-factor endpoints.  ``/admin/login/`` is included because it is another
# password prompt.  Everything else falls into public/read/write buckets.
_AUTH_EXACT = frozenset({
    '/login/',
    '/password-change/',
    '/admin/login/',
})
_AUTH_PREFIXES = ('/mfa/',)
_SKIP_PREFIXES = ('/static/', '/favicon.ico', '/admin/jsi18n/')


def request_limit_for(request):
    """Return the :class:`RateLimit` that applies to ``request``."""
    path = request.path
    method = request.method.upper()
    window = _setting('RATE_LIMIT_WINDOW', 60)
    authenticated = bool(
        getattr(request, 'user', None)
        and request.user.is_authenticated
    )

    if path in _AUTH_EXACT or path.startswith(_AUTH_PREFIXES):
        return RateLimit(
            'auth',
            _setting('RATE_LIMIT_AUTH', 10),
            window,
            backoff=True,
            backoff_base=_setting('RATE_LIMIT_AUTH_BACKOFF_BASE', 30),
            backoff_max=_setting('RATE_LIMIT_AUTH_BACKOFF_MAX', 900),
            backoff_multiplier=_setting('RATE_LIMIT_AUTH_BACKOFF_MULTIPLIER', 2),
        )
    if not authenticated:
        return RateLimit(
            'public',
            _setting('RATE_LIMIT_PUBLIC', 60),
            window,
        )
    if path.startswith('/search/'):
        return RateLimit(
            'search',
            _setting('RATE_LIMIT_SEARCH', 60),
            window,
        )
    if path.startswith('/media/'):
        return RateLimit(
            'media',
            _setting('RATE_LIMIT_MEDIA', 120),
            window,
        )
    if method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return RateLimit(
            'write',
            _setting('RATE_LIMIT_WRITE', 120),
            window,
        )
    return RateLimit(
        'read',
        _setting('RATE_LIMIT_READ', 1200),
        window,
    )


def should_skip_rate_limit(request):
    return (
        request.method == 'OPTIONS'
        or request.path.startswith(_SKIP_PREFIXES)
    )


def check_request_limit(request):
    """Consume one request from the applicable bucket.

    Returns ``0`` when the request is allowed, otherwise the number of seconds
    the caller should wait.  Auth buckets engage exponential backoff after the
    first over-limit request; other buckets simply report the rest of the
    fixed window.
    """
    limit = request_limit_for(request)
    identity = client_identity(request)
    key = f'grc:rl:{limit.bucket}:{identity}'
    blocked_key = f'{key}:blocked'
    now = timezone.now().timestamp()

    blocked_until = cache.get(blocked_key)
    if blocked_until:
        remaining = int(blocked_until - now)
        if remaining > 0:
            return remaining
        cache.delete(blocked_key)

    cache.add(key, 0, limit.window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, limit.window)
        count = 1

    if count <= limit.limit:
        return 0

    if not limit.backoff:
        return max(1, limit.window)

    strikes_key = f'{key}:strikes'
    strikes = cache.get(strikes_key, 0) + 1
    cache.set(strikes_key, strikes, max(limit.window, limit.backoff_max))
    delay = min(
        limit.backoff_max,
        limit.backoff_base * (limit.backoff_multiplier ** max(0, strikes - 1)),
    )
    cache.set(blocked_key, now + delay, delay)
    # Start a fresh window once the cool-down expires.  The strike counter is
    # intentionally not reset, so repeat abuse backs off further.
    cache.delete(key)
    logger.warning(
        'Rate limit backoff bucket=%s identity=%s strikes=%s delay=%ss',
        limit.bucket, identity, strikes, delay,
    )
    return delay


class FailureBackoff:
    """Count failures and return an exponentially increasing cool-down.

    A failure count is kept for ``window`` seconds.  Once it exceeds
    ``max_failures``, a retry-after timestamp is set.  The delay is
    ``base * multiplier ** (failures - max_failures - 1)``, capped at
    ``maximum``.  There is no permanent lock: after the delay expires the user
    may try again, and the counter decays with the window.
    """

    def __init__(
        self,
        namespace,
        *,
        max_failures,
        window,
        base,
        maximum,
        multiplier=2,
    ):
        self.namespace = namespace
        self.max_failures = max(1, int(max_failures))
        self.window = max(1, int(window))
        self.base = max(1, int(base))
        self.maximum = max(self.base, int(maximum))
        self.multiplier = max(1, int(multiplier))

    def _keys(self, identity):
        safe = str(identity or 'unknown')[:160]
        return (
            f'{self.namespace}:fails:{safe}',
            f'{self.namespace}:retry:{safe}',
        )

    def retry_after(self, identity):
        """Seconds until the next attempt, or ``0`` when not cooling down."""
        _, retry_key = self._keys(identity)
        until = cache.get(retry_key)
        if not until:
            return 0
        remaining = int(until - timezone.now().timestamp())
        if remaining <= 0:
            cache.delete(retry_key)
            return 0
        return remaining

    def register_failure(self, identity):
        """Record a failure and return the current failure count."""
        fail_key, retry_key = self._keys(identity)
        failures = (cache.get(fail_key) or 0) + 1
        cache.set(fail_key, failures, self.window)
        if failures >= self.max_failures:
            exponent = max(0, failures - self.max_failures)
            delay = min(
                self.maximum,
                self.base * (self.multiplier ** exponent),
            )
            cache.set(
                retry_key,
                timezone.now().timestamp() + delay,
                delay,
            )
        return failures

    def clear(self, identity):
        fail_key, retry_key = self._keys(identity)
        cache.delete_many([fail_key, retry_key])


def build_login_backoffs():
    """Build the per-account and per-IP login backoff helpers."""
    return (
        FailureBackoff(
            'grc:login-account',
            max_failures=_setting('LOGIN_MAX_FAILURES', 5),
            window=_setting('LOGIN_FAILURE_WINDOW', 900),
            base=_setting('LOGIN_BACKOFF_BASE_SECONDS', 30),
            maximum=_setting('LOGIN_BACKOFF_MAX_SECONDS', 900),
            multiplier=_setting('LOGIN_BACKOFF_MULTIPLIER', 2),
        ),
        FailureBackoff(
            'grc:login-ip',
            max_failures=_setting('LOGIN_IP_MAX_FAILURES', 20),
            window=_setting('LOGIN_FAILURE_WINDOW', 900),
            base=_setting('LOGIN_IP_BACKOFF_BASE_SECONDS', 60),
            maximum=_setting('LOGIN_IP_BACKOFF_MAX_SECONDS', 3600),
            multiplier=_setting('LOGIN_BACKOFF_MULTIPLIER', 2),
        ),
    )
