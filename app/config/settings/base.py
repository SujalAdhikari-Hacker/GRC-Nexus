"""Base settings shared by every environment.

Environment-specific modules (``dev`` and ``prod``) import from here and then
tighten or relax security. Every security switch is environment-overridable so
the same image can run locally over HTTP or behind TLS in production.
"""
from pathlib import Path
from sys import argv as _argv

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# True while the Django test runner is in charge. Used to switch off
# production-only behaviour (persistent DB connections, background jobs) that
# would otherwise stop the test database from being torn down cleanly.
_IS_TEST = 'test' in _argv

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)

# A short or well-known signing key makes password-reset tokens, sessions and
# the MFA helpers forgeable. Fail closed outside DEBUG instead of silently
# shipping a weak key.
_WEAK_SECRET_MARKERS = ('django-insecure', 'changeme', 'change-me', 'secret-key', 'password')
if not DEBUG and (
    len(SECRET_KEY) < 50
    or any(marker in SECRET_KEY.lower() for marker in _WEAK_SECRET_MARKERS)
):
    raise ImproperlyConfigured(
        'SECRET_KEY must be at least 50 characters and must not contain a '
        'well-known placeholder. Generate one with: '
        "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=Csv(),
)
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

# Kick off the ticket alert scan in a background thread when a user logs in.
# Disabled under the test runner: the thread opens its own database
# connection, which would otherwise keep the test database busy at teardown.
LOGIN_ALERT_SCAN = not _IS_TEST

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'guardian',
    'simple_history',
    'django_htmx',
    # Local apps
    'core',
    'frameworks',
    'assets',
    'vendors',
    'policies',
    'controls',
    'risks',
    'vulnerabilities',
    'kris',
    'audits',
    'threatintel',
    'tickets',
    'incidents',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.SecurityHeadersMiddleware',
    # Correlation id and full server-side exception logging wrap everything
    # that can fail. RequestValidation rejects malformed input before a view.
    'core.middleware.RequestIDMiddleware',
    'core.middleware.ErrorLoggingMiddleware',
    'core.middleware.CorsLockdownMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'core.middleware.RequestValidationMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Set the PostgreSQL RLS context before any view query runs.
    'core.middleware.RLSMiddleware',
    # Rate limits, MFA and forced password rotation run after authentication
    # so they can key on the user as well as the client address.
    'core.middleware.RateLimitMiddleware',
    'core.middleware.MFAEnforcementMiddleware',
    'core.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.UserTimezoneMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'tickets.context_processors.ticket_counters',
                'incidents.context_processors.incident_counters',
                'core.context_processors.pending_actions',
                'core.context_processors.notification_count',
                'core.context_processors.recent_notifications_context',
                'core.context_processors.notification_sections',
                'core.context_processors.user_preference_context',
                'core.context_processors.security_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
# Persistent connections are a production optimisation; they are disabled
# under test so the runner can drop the test database.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB'),
        # The application must connect as the non-superuser runtime role. The
        # POSTGRES_* role is the bootstrap/break-glass superuser used by the
        # database container and by operators; falling back to it here would
        # silently disable row-level security (superusers bypass FORCE RLS).
        'USER': config('DB_APP_USER'),
        'PASSWORD': config('DB_APP_PASSWORD'),
        'HOST': config('POSTGRES_HOST', default='db'),
        'PORT': config('POSTGRES_PORT', default='5432'),
        # Every Django connection starts with RLS bypassed so migrations and
        # management commands can operate. RLSMiddleware switches it off for
        # normal authenticated requests and restores it afterwards.
        'OPTIONS': {'options': '-c app.bypass_rls=on'},
        'CONN_MAX_AGE': 0 if _IS_TEST else config('DB_CONN_MAX_AGE', default=60, cast=int),
    }
}

# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
AUTH_USER_MODEL = 'core.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Explicitly keep the salted, deliberately-slow PBKDF2 hasher first. Django
# re-hashes legacy/weaker hashes on the next successful sign-in, so existing
# accounts are upgraded transparently.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# Password-reset links are single-use and short-lived.
PASSWORD_RESET_TIMEOUT = config('PASSWORD_RESET_TIMEOUT', default=3600, cast=int)

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)

# Multi-factor authentication (TOTP). MFA is opt-in per user; set
# MFA_REQUIRED_FOR_STAFF=true to force every staff/superuser to enrol.
MFA_ISSUER = config('MFA_ISSUER', default='GRC Nexus')
MFA_REQUIRED_FOR_STAFF = config('MFA_REQUIRED_FOR_STAFF', default=False, cast=bool)

# --------------------------------------------------------------------------
# i18n / tz
# --------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
# The timezone the *business* runs in. All date-based business logic uses
# ``timezone.localdate()``, so this switches when a risk becomes overdue, when
# a control's next test is due, and the date stamped on a closure — set it to
# the team's local zone (e.g. ``Asia/Kathmandu``) rather than leaving UTC.
TIME_ZONE = config('TIME_ZONE', default='UTC')
USE_I18N = True
USE_TZ = True

# Sign-in throttling and input limits are configured further down, next to
# the rate-limit block.

# --------------------------------------------------------------------------
# Static / media
# --------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# Serve uploaded media directly from Django. This is fine for a single-node
# deployment; in a larger setup put MEDIA behind object storage / a CDN.
SERVE_MEDIA = config('SERVE_MEDIA', default=False, cast=bool)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------------------------------------------------------------
# Auth redirects
# --------------------------------------------------------------------------
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'login'

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
# The default backend is the *console* backend: with no SMTP server
# configured, every digest/escalation is written to the container log, so the
# feature is observable out of the box (``docker compose logs -f web``). Set
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the host /
# credentials below to deliver real mail.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)
DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL', default='GRC Nexus <no-reply@grcnexus.local>'
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Absolute base URL used to build links inside emails — a scheduled job has no
# request to derive it from.
SITE_BASE_URL = config('SITE_BASE_URL', default='http://localhost:8000').rstrip('/')

# Escalations that have no obvious owner (no assigned user, no HOD) are sent
# here as a last resort. Comma-separated; empty means "drop them".
ESCALATION_FALLBACK_EMAILS = config(
    'ESCALATION_FALLBACK_EMAILS', default='', cast=Csv()
)

# --- scheduling knobs read by the send_email_digest / send_escalations jobs ---

# Only items seen since this many hours ago count as "new" digest activity.
DIGEST_LOOKBACK_HOURS = config('DIGEST_LOOKBACK_HOURS', default=24, cast=int)
# How long past a due date an item may sit before it escalates. Keeps a
# one-day slip out of the escalation queue.
ESCALATION_GRACE_DAYS = config('ESCALATION_GRACE_DAYS', default=1, cast=int)
# Risk exceptions / vendor contracts are warned about this many days ahead.
ESCALATION_WARN_DAYS = config('ESCALATION_WARN_DAYS', default=14, cast=int)

# --------------------------------------------------------------------------
# Security defaults (kept permissive here; prod.py tightens them).
# Anything with a config() call can be overridden per-environment.
# --------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='Lax')
# Eight hours: long enough for a working day, short enough that a stolen
# session does not remain valid for Django's two-week default.
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', default=8 * 60 * 60, cast=int)
CSRF_COOKIE_SAMESITE = 'Lax'
# The CSRF cookie is intentionally readable by same-origin JavaScript so the
# HTMX header can echo it. It is not an authentication token.
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'

# No cross-origin browser API is exposed. Keep this list empty unless a
# deliberate, reviewed integration needs it; credentials are never allowed.
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

# Application-layer rate limits (per process; point CACHES at Redis for a
# multi-worker deployment). Disabled under the test runner so the suite is
# deterministic; individual tests override RATE_LIMIT_ENABLED.
RATE_LIMIT_ENABLED = config(
    'RATE_LIMIT_ENABLED', default=not _IS_TEST, cast=bool
)
# Per-IP auth requests (login, password change, MFA).  The account-specific
# login counter and exponential delay live in core.login_throttle; the MFA
# views have their own per-user counter.
RATE_LIMIT_AUTH = config('RATE_LIMIT_AUTH', default=10, cast=int)
RATE_LIMIT_PUBLIC = config('RATE_LIMIT_PUBLIC', default=60, cast=int)
RATE_LIMIT_SEARCH = config('RATE_LIMIT_SEARCH', default=60, cast=int)
RATE_LIMIT_MEDIA = config('RATE_LIMIT_MEDIA', default=120, cast=int)
RATE_LIMIT_WRITE = config('RATE_LIMIT_WRITE', default=120, cast=int)
RATE_LIMIT_READ = config('RATE_LIMIT_READ', default=1200, cast=int)
RATE_LIMIT_WINDOW = config('RATE_LIMIT_WINDOW', default=60, cast=int)
RATE_LIMIT_AUTH_BACKOFF_BASE = config(
    'RATE_LIMIT_AUTH_BACKOFF_BASE', default=30, cast=int
)
RATE_LIMIT_AUTH_BACKOFF_MAX = config(
    'RATE_LIMIT_AUTH_BACKOFF_MAX', default=900, cast=int
)
RATE_LIMIT_AUTH_BACKOFF_MULTIPLIER = config(
    'RATE_LIMIT_AUTH_BACKOFF_MULTIPLIER', default=2, cast=int
)

# Sign-in failure backoff.  A successful sign-in clears the account counter;
# the per-IP counter decays with LOGIN_FAILURE_WINDOW so one valid account
# cannot reset credential-stuffing protection for the whole address.
LOGIN_MAX_FAILURES = config('LOGIN_MAX_FAILURES', default=5, cast=int)
LOGIN_FAILURE_WINDOW = config('LOGIN_FAILURE_WINDOW', default=900, cast=int)
LOGIN_BACKOFF_BASE_SECONDS = config(
    'LOGIN_BACKOFF_BASE_SECONDS', default=30, cast=int
)
LOGIN_BACKOFF_MAX_SECONDS = config(
    'LOGIN_BACKOFF_MAX_SECONDS', default=900, cast=int
)
LOGIN_BACKOFF_MULTIPLIER = config(
    'LOGIN_BACKOFF_MULTIPLIER', default=2, cast=int
)
LOGIN_IP_MAX_FAILURES = config('LOGIN_IP_MAX_FAILURES', default=20, cast=int)
LOGIN_IP_BACKOFF_BASE_SECONDS = config(
    'LOGIN_IP_BACKOFF_BASE_SECONDS', default=60, cast=int
)
LOGIN_IP_BACKOFF_MAX_SECONDS = config(
    'LOGIN_IP_BACKOFF_MAX_SECONDS', default=3600, cast=int
)
LOGIN_USERNAME_MAX_LENGTH = config(
    'LOGIN_USERNAME_MAX_LENGTH', default=150, cast=int
)
LOGIN_PASSWORD_MAX_LENGTH = config(
    'LOGIN_PASSWORD_MAX_LENGTH', default=4096, cast=int
)

# Second-factor failures use the same exponential model.
MFA_MAX_FAILURES = config('MFA_MAX_FAILURES', default=5, cast=int)
MFA_FAILURE_WINDOW = config('MFA_FAILURE_WINDOW', default=300, cast=int)
MFA_BACKOFF_BASE_SECONDS = config(
    'MFA_BACKOFF_BASE_SECONDS', default=30, cast=int
)
MFA_BACKOFF_MAX_SECONDS = config(
    'MFA_BACKOFF_MAX_SECONDS', default=900, cast=int
)
MFA_BACKOFF_MULTIPLIER = config(
    'MFA_BACKOFF_MULTIPLIER', default=2, cast=int
)
MFA_IP_MAX_FAILURES = config('MFA_IP_MAX_FAILURES', default=20, cast=int)

# Strict input limits (bytes/characters, not a substitute for form validation).
INPUT_MAX_PATH_LENGTH = config(
    'INPUT_MAX_PATH_LENGTH', default=2048, cast=int
)
INPUT_MAX_QUERY_STRING_LENGTH = config(
    'INPUT_MAX_QUERY_STRING_LENGTH', default=4096, cast=int
)
INPUT_MAX_QUERY_PARAMS = config(
    'INPUT_MAX_QUERY_PARAMS', default=50, cast=int
)
INPUT_MAX_QUERY_VALUE_LENGTH = config(
    'INPUT_MAX_QUERY_VALUE_LENGTH', default=1000, cast=int
)
INPUT_MAX_FORM_FIELDS = config(
    'INPUT_MAX_FORM_FIELDS', default=2000, cast=int
)
INPUT_MAX_FORM_VALUE_LENGTH = config(
    'INPUT_MAX_FORM_VALUE_LENGTH', default=100_000, cast=int
)
INPUT_MAX_FILENAME_LENGTH = config(
    'INPUT_MAX_FILENAME_LENGTH', default=255, cast=int
)

# Outbound fetches (threat-intel / vulnerability enrichment) are restricted to
# these hosts. This is a defence-in-depth allowlist on top of the private-IP
# and redirect checks in core.safe_http.
SAFE_HTTP_ALLOWED_HOSTS = config(
    'SAFE_HTTP_ALLOWED_HOSTS',
    default=(
        'raw.githubusercontent.com,otx.alienvault.com,threatcluster.io,'
        'threatfox-api.abuse.ch,services.nvd.nist.gov,api.first.org,'
        'www.cisa.gov,cisa.gov'
    ),
    cast=Csv(),
)
SAFE_HTTP_TIMEOUT = config('SAFE_HTTP_TIMEOUT', default=20, cast=int)
SAFE_HTTP_MAX_BYTES = config(
    'SAFE_HTTP_MAX_BYTES', default=25 * 1024 * 1024, cast=int
)

# Shared secret for inbound signed webhooks (HMAC-SHA256). Empty disables the
# verifier; no inbound webhook route ships enabled by default.
WEBHOOK_SECRET = config('WEBHOOK_SECRET', default='')

# Upload limits (defend against memory-exhaustion via huge POSTs).
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    'DATA_UPLOAD_MAX_MEMORY_SIZE', default=10 * 1024 * 1024, cast=int
)
FILE_UPLOAD_MAX_MEMORY_SIZE = config(
    'FILE_UPLOAD_MAX_MEMORY_SIZE', default=5 * 1024 * 1024, cast=int
)
FILE_UPLOAD_PERMISSIONS = 0o640
DATA_UPLOAD_MAX_NUMBER_FIELDS = config(
    'DATA_UPLOAD_MAX_NUMBER_FIELDS', default=2000, cast=int
)
DATA_UPLOAD_MAX_NUMBER_FILES = config(
    'DATA_UPLOAD_MAX_NUMBER_FILES', default=20, cast=int
)
# Evidence/document validator cap.  Keep it below the generic upload limit so
# an oversized evidence file is rejected with a clear field error.
MAX_EVIDENCE_UPLOAD_SIZE = config(
    'MAX_EVIDENCE_UPLOAD_SIZE', default=10 * 1024 * 1024, cast=int
)
MAX_EVIDENCE_FILENAME_LENGTH = config(
    'MAX_EVIDENCE_FILENAME_LENGTH', default=255, cast=int
)

# --------------------------------------------------------------------------
# Logging — console only; the platform (Docker/systemd) collects it.
# --------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'filters': {
        'redact_sensitive': {
            '()': 'core.logging_filters.SensitiveDataFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['redact_sensitive'],
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # WeasyPrint pulls in fontTools, whose INFO-level glyph-subset logging
        # floods the console on every PDF render. It is not useful in production.
        'fontTools': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'weasyprint': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
