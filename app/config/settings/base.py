"""Base settings shared by every environment.

Environment-specific modules (``dev`` and ``prod``) import from here and then
tighten or relax security. Every security switch is environment-overridable so
the same image can run locally over HTTP or behind TLS in production.
"""
from pathlib import Path
from sys import argv as _argv

from decouple import Csv, config

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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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
                'core.context_processors.pending_actions',
                'core.context_processors.notification_count',
                'core.context_processors.recent_notifications_context',
                'core.context_processors.notification_sections',
                'core.context_processors.user_preference_context',
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
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': config('POSTGRES_HOST', default='db'),
        'PORT': config('POSTGRES_PORT', default='5432'),
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
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)

# --------------------------------------------------------------------------
# i18n / tz
# --------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

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
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Upload limits (defend against memory-exhaustion via huge POSTs).
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    'DATA_UPLOAD_MAX_MEMORY_SIZE', default=10 * 1024 * 1024, cast=int
)
FILE_UPLOAD_MAX_MEMORY_SIZE = config(
    'FILE_UPLOAD_MAX_MEMORY_SIZE', default=5 * 1024 * 1024, cast=int
)
FILE_UPLOAD_PERMISSIONS = 0o640

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
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
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
