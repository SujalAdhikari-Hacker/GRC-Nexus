"""Production settings.

Secure by default for a real deployment, but the bundled Docker Compose stack
serves plain HTTP on localhost. One switch controls the HTTPS posture:

    USE_TLS=true

Set it once the app is behind a TLS-terminating reverse proxy (Caddy, nginx,
Traefik, a cloud load balancer). It turns on the secure-cookie flags, the HTTP
to HTTPS redirect and HSTS. Individual switches can still be overridden for
staged rollouts - see docs/DEPLOYMENT.md.

Leaving USE_TLS unset keeps the local HTTP stack working. Never deploy a
public host with USE_TLS=false: cookies would travel in clear text.
"""
from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = config('DEBUG', default=False, cast=bool)

# --------------------------------------------------------------------------
# TLS / cookies
# --------------------------------------------------------------------------
USE_TLS = config('USE_TLS', default=False, cast=bool)

SECURE_SSL_REDIRECT = config(
    'SECURE_SSL_REDIRECT', default=USE_TLS, cast=bool
)
SESSION_COOKIE_SECURE = config(
    'SESSION_COOKIE_SECURE', default=USE_TLS, cast=bool
)
CSRF_COOKIE_SECURE = config(
    'CSRF_COOKIE_SECURE', default=USE_TLS, cast=bool
)

# HSTS: one year once TLS is on. Start smaller if you are still validating the
# certificate chain (e.g. 3600), then raise it. The preload *header* is harmless
# on its own - it only takes effect after you submit the domain to the browser
# preload list, which is a separate and hard-to-undo decision.
SECURE_HSTS_SECONDS = config(
    'SECURE_HSTS_SECONDS', default=31_536_000 if USE_TLS else 0, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    'SECURE_HSTS_INCLUDE_SUBDOMAINS', default=USE_TLS, cast=bool
)
SECURE_HSTS_PRELOAD = config(
    'SECURE_HSTS_PRELOAD', default=USE_TLS, cast=bool
)

# gunicorn speaks plain HTTP, so a TLS deployment is always behind a proxy that
# terminates TLS and sets X-Forwarded-Proto. Trust that header only when TLS is
# enabled (or when explicitly asked for); otherwise a client could spoof it.
if config('USE_X_FORWARDED_PROTO', default=USE_TLS, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Uploaded evidence is served by Django's authorised view (core.media), which
# enforces login and department scoping. A reverse proxy must not map /media/
# directly: that would bypass the check.
