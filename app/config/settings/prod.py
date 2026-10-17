"""Production settings.

Secure by default, but every switch can be relaxed with an environment
variable so the bundled Docker Compose stack can run over plain HTTP on
localhost while a real TLS deployment keeps the hardened defaults.
"""
from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = config('DEBUG', default=False, cast=bool)

# TLS / cookies -----------------------------------------------------------------
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool
)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# Only trust X-Forwarded-Proto when we are actually behind a TLS proxy.
if config('USE_X_FORWARDED_PROTO', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Media is normally served by the reverse proxy / object storage in prod.
SERVE_MEDIA = config('SERVE_MEDIA', default=False, cast=bool)
