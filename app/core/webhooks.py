"""Signed webhook verification.

No inbound webhook route is enabled in the shipped product, but integrations
that POST into GRC Nexus must be able to prove authenticity. Use the
``X-GRC-Signature`` header format::

    t=<unix-seconds>,v1=<hex hmac-sha256 of "t.<raw body>">

The timestamp is checked against a replay window, and the comparison is
constant-time. The secret comes from ``WEBHOOK_SECRET`` and never leaves the
server.
"""
import hashlib
import hmac
import time


class WebhookVerificationError(ValueError):
    """Raised when a webhook signature is missing, stale or invalid."""


def sign_payload(secret, timestamp, payload):
    """Return the hex HMAC-SHA256 for ``timestamp`` + raw ``payload``."""
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    message = f'{int(timestamp)}.'.encode('utf-8') + payload
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def parse_signature_header(header):
    """Parse ``t=...,v1=...`` into ``(timestamp, signature)``."""
    parts = {}
    for item in (header or '').split(','):
        if '=' not in item:
            continue
        key, value = item.split('=', 1)
        parts[key.strip()] = value.strip()
    if 't' not in parts or 'v1' not in parts:
        raise WebhookVerificationError('Malformed signature header.')
    try:
        timestamp = int(parts['t'])
    except (TypeError, ValueError) as exc:
        raise WebhookVerificationError('Invalid signature timestamp.') from exc
    return timestamp, parts['v1']


def verify_signature(payload, header, secret, *, tolerance=300, now=None):
    """Return ``True`` for a valid signature, otherwise raise."""
    if not secret:
        raise WebhookVerificationError('Webhook signing secret is not configured.')
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    timestamp, provided = parse_signature_header(header)
    current = int(now if now is not None else time.time())
    if abs(current - timestamp) > tolerance:
        raise WebhookVerificationError('Webhook signature has expired.')
    expected = sign_payload(secret, timestamp, payload)
    if not hmac.compare_digest(expected, provided):
        raise WebhookVerificationError('Webhook signature is invalid.')
    return True
