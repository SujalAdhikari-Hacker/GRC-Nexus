"""Security middleware: headers/CSP, CORS lockdown, rate limits, MFA and
forced password rotation.

The project deliberately avoids a dependency on django-csp and django-cors-
headers. The policies here are small, explicit and testable, and they fail
closed (no CORS headers unless an origin is explicitly configured).
"""
import secrets
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                pref = getattr(request.user, 'preference', None)
                if pref and pref.timezone:
                    timezone.activate(pref.timezone)
            except Exception:
                pass
        return self.get_response(request)


class RLSMiddleware:
    """Set the PostgreSQL row-level-security context for each request.

    Django connections start with ``app.bypass_rls = 'on'`` (configured in
    ``DATABASES['default']['OPTIONS']``) so management commands and migrations
    are not constrained. Ordinary requests - including anonymous ones - switch
    it off; authenticated requests also supply their department/user. Superusers
    keep the bypass. The values are reset in ``finally`` so a reused connection
    cannot inherit them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _set_context(bypass, department_id, user_id):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT set_config('app.bypass_rls', %s, false),
                       set_config('app.department_id', %s, false),
                       set_config('app.user_id', %s, false)
                """,
                [bypass, department_id, user_id],
            )

    @staticmethod
    def _context_for_user(user):
        if user is not None and user.is_authenticated and user.is_superuser:
            return 'on', '', ''
        if user is not None and user.is_authenticated:
            return 'off', str(user.department_id or ''), str(user.pk)
        return 'off', '', ''

    @classmethod
    def activate_for_user(cls, user):
        """Refresh the DB context after a view logs a user in mid-request."""
        if connection.vendor != 'postgresql':
            return
        cls._set_context(*cls._context_for_user(user))

    def __call__(self, request):
        if connection.vendor != 'postgresql':
            return self.get_response(request)

        user = getattr(request, 'user', None)
        # Fail closed for anonymous traffic as well: a missed login check must
        # not expose department-owned rows just because there is no user
        # context. Authentication itself queries only the excluded
        # ``core_user`` table.
        self._set_context(*self._context_for_user(user))
        try:
            return self.get_response(request)
        finally:
            self._set_context('on', '', '')


# ---------------------------------------------------------------------------
# Security headers / Content-Security-Policy
# ---------------------------------------------------------------------------

_CSP_APP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "style-src-attr 'unsafe-inline'; "
    "script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://unpkg.com; "
    "script-src-attr 'none'; "
    "connect-src 'self'; "
    "media-src 'self'; "
    "worker-src 'self' blob:; "
    "manifest-src 'self'"
)

# Django admin ships its own inline bootstrap script; allow it on that path
# only. Admin output is framework-controlled and still auto-escaped.
_CSP_ADMIN = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'"
)


class SecurityHeadersMiddleware:
    """Attach a nonce-based CSP and other browser hardening headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        response = self.get_response(request)

        nonce = getattr(request, 'csp_nonce', '')
        if request.path.startswith('/admin/'):
            csp = _CSP_ADMIN
        else:
            csp = _CSP_APP.format(nonce=nonce)
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), payment=(), '
            'usb=(), interest-cohort=()'
        )
        return response


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class CorsLockdownMiddleware:
    """Emit CORS headers only for explicitly allowlisted origins.

    No cross-origin API is exposed by default. Credentials are never allowed;
    a future API must use a token, not the session cookie.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        origin = request.headers.get('Origin')
        allowed = {o.strip().rstrip('/') for o in getattr(settings, 'CORS_ALLOWED_ORIGINS', [])}
        if origin and origin.rstrip('/') in allowed:
            response.headers['Access-Control-Allow-Origin'] = origin
            existing = response.headers.get('Vary', '')
            response.headers['Vary'] = f'{existing}, Origin'.strip(', ') if existing else 'Origin'
        else:
            response.headers.pop('Access-Control-Allow-Origin', None)
            response.headers.pop('Access-Control-Allow-Credentials', None)
        return response


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _client_identity(request):
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return f'u{request.user.pk}'
    return f'ip{request.META.get("REMOTE_ADDR", "unknown")}'


def _bucket(path, method):
    if path in ('/login/', '/password-change/') or path.startswith('/mfa/'):
        return 'auth', getattr(settings, 'RATE_LIMIT_AUTH', 20)
    if path.startswith('/search/'):
        return 'search', getattr(settings, 'RATE_LIMIT_SEARCH', 60)
    if path.startswith('/media/'):
        return 'media', getattr(settings, 'RATE_LIMIT_MEDIA', 120)
    if method.upper() in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return 'write', getattr(settings, 'RATE_LIMIT_WRITE', 120)
    return 'read', getattr(settings, 'RATE_LIMIT_READ', 1200)


class RateLimitMiddleware:
    """Fixed-window request limiting for auth, search, media and writes.

    The default cache is per-process. For a multi-worker deployment set
    ``CACHES`` to Redis so the limit is shared by every worker.
    """

    SKIP_PREFIXES = ('/static/', '/favicon.ico', '/admin/jsi18n/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'RATE_LIMIT_ENABLED', False):
            return self.get_response(request)
        if request.method == 'OPTIONS' or request.path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)

        window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
        bucket, limit = _bucket(request.path, request.method)
        key = f'grc:rl:{bucket}:{_client_identity(request)}'
        cache.add(key, 0, window)
        count = cache.get(key, 0)
        if count >= limit:
            response = render(
                request,
                '429.html',
                {'request_path': request.path, 'retry_after': window},
                status=429,
            )
            response.headers['Retry-After'] = str(window)
            return response
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, window)
        return self.get_response(request)


# ---------------------------------------------------------------------------
# MFA / forced password change
# ---------------------------------------------------------------------------

class MFAEnforcementMiddleware:
    """Keep a password-authenticated session in a pre-MFA state.

    ``ThrottledLoginView`` marks sessions of MFA-enabled users as unverified;
    every route except the verifier, logout and static/media is redirected to
    the verifier until the second factor succeeds.
    """

    EXEMPT_PREFIXES = ('/mfa/', '/logout/', '/login/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            mfa = getattr(user, 'mfa', None)
            enabled = bool(mfa and mfa.enabled)
            exempt = request.path.startswith(self.EXEMPT_PREFIXES)
            if enabled and not request.session.get('mfa_verified', False) and not exempt:
                target = reverse('core:mfa_verify')
                next_url = quote(request.get_full_path(), safe='/')
                return redirect(f'{target}?next={next_url}')
            if (
                not enabled
                and getattr(settings, 'MFA_REQUIRED_FOR_STAFF', False)
                and (user.is_staff or user.is_superuser)
                and not exempt
            ):
                return redirect('core:mfa_setup')
        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """Force accounts still using a seeded/default password to rotate it."""

    EXEMPT_PREFIXES = (
        '/password-change/', '/logout/', '/login/', '/mfa/', '/static/', '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, 'must_change_password', False)
            and not request.path.startswith(self.EXEMPT_PREFIXES)
        ):
            return redirect('password_change')
        return self.get_response(request)
