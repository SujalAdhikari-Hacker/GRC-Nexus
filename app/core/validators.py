"""Reusable upload validators.

Uploaded evidence is attacker-reachable input: an authenticated low-privilege
user can post any file. We restrict extensions and cap size so the app cannot
be used to store executables or exhaust disk.
"""
import os

from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EVIDENCE_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
    '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.md', '.json',
    '.zip', '.log', '.eml', '.msg', '.pcap', '.xml', '.yaml', '.yml',
}


def validate_evidence_file(value):
    """Validate an uploaded evidence file (extension + size)."""
    name = getattr(value, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EVIDENCE_EXTENSIONS:
        raise ValidationError(
            f'Unsupported file type "{ext or name}". Allowed types: '
            + ', '.join(sorted(ALLOWED_EVIDENCE_EXTENSIONS))
            + '.'
        )
    size = getattr(value, 'size', None)
    if size is not None and size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            f'File is too large ({size / (1024 * 1024):.1f} MB). '
            f'Maximum allowed size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.'
        )


# URL schemes that are safe to place in a link. Anything else — notably
# ``javascript:`` and ``data:`` — is refused, because the value is rendered
# straight into an ``href``: a stored ``javascript:`` URL is click-to-run XSS.
_ALLOWED_URL_SCHEMES = ('http', 'https')


def is_safe_external_url(value):
    """True when ``value`` may be used as a link target.

    Accepts http(s) URLs and relative/drive-letter paths; refuses scriptable
    schemes. Shared by the model validator and the display helper so the two
    can never drift apart.
    """
    value = (value or '').strip()
    if not value:
        return True
    from urllib.parse import urlparse

    scheme = urlparse(value).scheme.lower()
    if not scheme or scheme in _ALLOWED_URL_SCHEMES:
        return True
    # A single letter is a Windows drive (``C:\evidence\x.pdf``), not a scheme.
    return len(scheme) == 1


def validate_external_url(value):
    """Reject scriptable URL schemes in a user-supplied link target."""
    if not is_safe_external_url(value):
        raise ValidationError(
            'Enter an http(s) URL or a file path. Scriptable URLs such as '
            '"javascript:" or "data:" are not allowed.',
            code='unsafe_url_scheme',
        )
