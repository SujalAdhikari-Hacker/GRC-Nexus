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
