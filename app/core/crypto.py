"""Symmetric encryption for secrets stored in the database.

The SMTP password is encrypted with a key derived from ``SECRET_KEY`` so a
database dump does not expose it in clear text. Rotating ``SECRET_KEY``
invalidates stored passwords: re-enter the SMTP password after a rotation.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    digest = hashlib.sha256(
        f'grc-nexus-email:{settings.SECRET_KEY}'.encode('utf-8')
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    """Encrypt ``value``; an empty value stays empty."""
    if not value:
        return ''
    return _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_secret(value: str) -> str:
    """Decrypt ``value``; a corrupt or rotated key yields an empty string."""
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError):
        return ''
