"""
Run the alert scan once when a user logs in.
Cheap enough for a small DB, keeps tickets fresh without a scheduler.
"""
import threading
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


def _run_scan():
    """Run in a background thread so login stays fast."""
    try:
        from .alerts import scan_and_create_tickets
        scan_and_create_tickets(verbose=False)
    except Exception:
        pass  # never break login


@receiver(user_logged_in)
def trigger_scan_on_login(sender, request, user, **kwargs):
    # Run in background so the login redirect isn't delayed
    threading.Thread(target=_run_scan, daemon=True).start()