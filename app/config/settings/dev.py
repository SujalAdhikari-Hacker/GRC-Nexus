"""Local development settings.

Permissive: no HTTPS, no secure cookies, verbose errors. Never use in
production.
"""
from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS', default='localhost,127.0.0.1,0.0.0.0', cast=lambda v: [s.strip() for s in v.split(',')]
)

# No TLS in local dev.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
