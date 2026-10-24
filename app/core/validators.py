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


# Magic bytes for formats where the extension alone is not trustworthy. A
# polyglot or renamed executable must not be stored just because it ends in
# ``.pdf``. Text-like formats (csv/txt/md/json/xml/yaml/log/eml) have no
# reliable signature and are always served as attachments.
_ZIP_MAGIC = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')
_OLE_MAGIC = (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',)
_MAGIC_BY_EXTENSION = {
    '.pdf': (b'%PDF-',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.gif': (b'GIF87a', b'GIF89a'),
    '.bmp': (b'BM',),
    '.zip': _ZIP_MAGIC,
    '.docx': _ZIP_MAGIC,
    '.xlsx': _ZIP_MAGIC,
    '.doc': _OLE_MAGIC,
    '.xls': _OLE_MAGIC,
    '.msg': _OLE_MAGIC,
    '.pcap': (
        b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1',
        b'\xa1\xb2\x3c\x4d',
    ),
}


def _read_head(value, length=16):
    """Read the first bytes of an upload without consuming the stream."""
    try:
        position = value.tell()
    except Exception:
        position = None
    try:
        value.seek(0)
        return value.read(length)
    finally:
        if position is not None:
            try:
                value.seek(position)
            except Exception:
                pass


def _magic_matches(ext, head):
    if ext == '.webp':
        return len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WEBP'
    expected = _MAGIC_BY_EXTENSION.get(ext)
    if not expected:
        return True
    return any(head.startswith(signature) for signature in expected)


def validate_evidence_file(value):
    """Validate an uploaded evidence file (extension, magic bytes + size)."""
    name = getattr(value, 'name', '') or ''
    normalized = name.replace('\\', '/')
    if '\x00' in name or '..' in normalized.split('/'):
        raise ValidationError('The file name is not valid.')
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
    if size == 0:
        raise ValidationError('The uploaded file is empty.')
    head = _read_head(value)
    if not _magic_matches(ext, head):
        raise ValidationError(
            f'The contents of this file do not match its "{ext}" extension. '
            'Upload a genuine PDF, image, archive or office document.'
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
