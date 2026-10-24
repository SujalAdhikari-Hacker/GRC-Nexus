"""TOTP (RFC 6238) helpers used by the MFA views.

Implemented with the standard library only: no extra service, no QR-image
dependency and no secret ever leaves the server. The enrolment page displays
the base32 secret and an ``otpauth://`` URI, both of which every mainstream
authenticator app accepts via manual entry.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DEFAULT_STEP = 30
DEFAULT_DIGITS = 6


def generate_secret(num_bytes=20):
    """Return a new base32 TOTP secret (160 bits, no padding)."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode('ascii').rstrip('=')


def _decode_secret(secret):
    padded = secret.strip().upper()
    padded += '=' * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_code(secret, at=None, step=DEFAULT_STEP, digits=DEFAULT_DIGITS):
    """Return the TOTP for ``at`` (a UNIX timestamp or datetime)."""
    if at is None:
        at = time.time()
    elif hasattr(at, 'timestamp'):
        at = at.timestamp()
    counter = int(at) // step
    digest = hmac.new(
        _decode_secret(secret),
        struct.pack('>Q', counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def verify_totp(secret, code, at=None, window=1, step=DEFAULT_STEP, digits=DEFAULT_DIGITS):
    """Verify ``code`` allowing ``window`` steps of clock drift either way."""
    code = (code or '').strip().replace(' ', '')
    if not code.isdigit() or len(code) != digits:
        return False
    if at is None:
        at = time.time()
    elif hasattr(at, 'timestamp'):
        at = at.timestamp()
    for offset in range(-window, window + 1):
        if hmac.compare_digest(
            totp_code(secret, at=at + offset * step, step=step, digits=digits),
            code,
        ):
            return True
    return False


def build_otpauth_uri(secret, account_name, issuer='GRC Nexus'):
    """Build the standard ``otpauth://totp/...`` enrolment URI."""
    label = quote(f'{issuer}:{account_name}', safe='')
    query = urlencode({
        'secret': secret,
        'issuer': issuer,
        'algorithm': 'SHA1',
        'digits': DEFAULT_DIGITS,
        'period': DEFAULT_STEP,
    })
    return f'otpauth://totp/{label}?{query}'


def generate_backup_codes(count=10):
    """Return human-friendly one-time backup codes (e.g. ``A1B2-C3D4``)."""
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()
        codes.append(f'{raw[:4]}-{raw[4:]}')
    return codes


def normalize_backup_code(code):
    return (code or '').strip().replace(' ', '').replace('-', '').upper()
