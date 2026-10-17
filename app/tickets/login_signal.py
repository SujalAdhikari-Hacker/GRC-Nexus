"""
Run the ticket alert scan shortly after a user logs in.

The scan is kept off the request path so a login is never delayed, but it is
made safe:

* failures are logged instead of being swallowed;
* the worker thread closes the database connection it opened. Connections are
  thread-local in Django, so nothing else will close it — an unclosed one
  leaks a connection per login and keeps the test database busy at teardown;
* runs are throttled, so a burst of logins does not start several concurrent
  full-database scans (which could also race and create duplicate tickets);
* the whole thing can be switched off with ``settings.LOGIN_ALERT_SCAN``
  (it is off under the test runner).
"""
import logging
import threading

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.db import connections
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# One scan per process per window is plenty — the dashboard also refreshes
# tickets, and a management command exists for scheduled runs.
SCAN_THROTTLE_SECONDS = 60
_THROTTLE_KEY = 'grc:login-alert-scan'


def run_login_alert_scan():
    """Run one alert scan, always releasing this thread's DB connection."""
    try:
        from .alerts import scan_and_create_tickets
        scan_and_create_tickets(verbose=False)
    except Exception:
        logger.exception('Login-triggered ticket alert scan failed')
    finally:
        connections.close_all()


@receiver(user_logged_in)
def trigger_scan_on_login(sender, request, user, **kwargs):
    if not getattr(settings, 'LOGIN_ALERT_SCAN', True):
        return
    if cache.get(_THROTTLE_KEY) is not None:
        return
    cache.set(_THROTTLE_KEY, 1, SCAN_THROTTLE_SECONDS)
    threading.Thread(target=run_login_alert_scan, daemon=True).start()
