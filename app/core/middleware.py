"""Security middleware: headers/CSP, CORS lockdown, rate limits, MFA and
forced password rotation.

The project deliberately avoids a dependency on django-csp and django-cors-
headers. The policies here are small, explicit and testable, and they fail
closed (no CORS headers unless an origin is explicitly configured).
"""
import logging
import secrets
import uuid
from urllib.parse import quote

from django.conf import settings
from django.db import connection
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .input_validation import InvalidInput, validate_request
from .rate_limit import check_request_limit, should_skip_rate_limit

logger = logging.getLogger(__name__)


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
    def _set_context(bypass, department_id, user_id, org_read='off'):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT set_config('app.bypass_rls', %s, false),
                       set_config('app.department_id', %s, false),
                       set_config('app.user_id', %s, false),
                       set_config('app.org_read', %s, false)
                """,
                [bypass, department_id, user_id, org_read],
            )

    @staticmethod
    def _context_for_user(user):
        if user is not None and user.is_authenticated and user.is_superuser:
            return 'on', '', '', 'on'
        if user is not None and user.is_authenticated:
            dept = getattr(user, 'department', None)
            org_read = 'on' if (dept and getattr(dept, 'has_org_read_oversight', False)) else 'off'
            return 'off', str(user.department_id or ''), str(user.pk), org_read
        return 'off', '', '', 'off'

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
            self._set_context('on', '', '', 'off')


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
# Request validation / error context
# ---------------------------------------------------------------------------

class RequestIDMiddleware:
    """Give every request a correlation id and return it to the caller."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = (request.headers.get('X-Request-ID') or '').strip()
        if supplied and len(supplied) <= 128 and supplied.isprintable():
            request.request_id = supplied
        else:
            request.request_id = uuid.uuid4().hex
        response = self.get_response(request)
        response.headers.setdefault('X-Request-ID', request.request_id)
        return response


class RequestValidationMiddleware:
    """Reject malformed requests before they reach a view.

    This is a transport-level schema: path/query length, parameter names and
    value length, control characters, form content type and field sizes.  The
    domain-level schema (required fields, choices, dates, files) is enforced by
    Django forms and the explicit validators in ``core.input_validation``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            validate_request(request)
        except InvalidInput as exc:
            logger.warning(
                'Rejected invalid request method=%s path=%s reason=%s',
                request.method, request.path, exc,
            )
            # This middleware runs before AuthenticationMiddleware, so make
            # sure template context processors see an anonymous user rather
            # than crashing on a missing attribute.
            if not hasattr(request, 'user'):
                from django.contrib.auth.models import AnonymousUser
                request.user = AnonymousUser()
            return render(
                request,
                '400.html',
                {'request_path': request.path},
                status=400,
            )
        return self.get_response(request)


class ErrorLoggingMiddleware:
    """Log unexpected exceptions with full detail before Django renders 500.

    The exception is re-raised so Django's normal error handling (including
    ``DEBUG`` behaviour and the custom 500 handler) is preserved.  Users never
    receive this log line; it is server-side only.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            user = getattr(request, 'user', None)
            logger.exception(
                'Unhandled request error request_id=%s method=%s path=%s user=%s',
                getattr(request, 'request_id', '-'),
                request.method,
                request.path,
                getattr(user, 'pk', 'anonymous'),
            )
            raise


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class RateLimitMiddleware:
    """Apply the configurable request buckets from :mod:`core.rate_limit`.

    Auth routes are keyed per IP (the account-level backoff lives in
    ``core.login_throttle`` and the MFA views), use a stricter limit and engage
    exponential backoff.  Public routes get a moderate per-IP limit; signed-in
    reads/writes are keyed per user and are intentionally looser.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'RATE_LIMIT_ENABLED', False):
            return self.get_response(request)
        if should_skip_rate_limit(request):
            return self.get_response(request)

        retry_after = check_request_limit(request)
        if retry_after:
            response = render(
                request,
                '429.html',
                {
                    'request_path': request.path,
                    'retry_after': retry_after,
                },
                status=429,
            )
            response.headers['Retry-After'] = str(retry_after)
            return response
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
