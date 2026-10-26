"""Strict input helpers used by the request middleware and high-risk views.

Django forms remain the primary schema for model-backed forms.  This module
covers the two gaps forms do not close on their own:

* transport-level limits for every query string and form body, and
* typed helpers for views that read raw ``request.GET``/``request.POST``
  values (score previews, sharing, saved views, bulk actions, MFA codes).

Invalid input raises :class:`InvalidInput` (a ``SuspiciousOperation``), which
Django turns into a generic 400 response.  Values are rejected rather than
silently coerced, so a caller cannot smuggle an unexpected type or an
over-long value past a view.
"""
from __future__ import annotations

import re

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

# C0 controls except tab, newline and carriage return.  NUL is the important
# one for filesystem/DB safety; the rest make logs and UI confusing.
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_QUERY_KEY_RE = re.compile(r'^[A-Za-z0-9_.:\-\[\]]{1,80}$')
_FORM_KEY_RE = re.compile(r'^[A-Za-z0-9_.:\-\[\]]{1,100}$')
_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,100}$')
_TOTP_RE = re.compile(r'^\d{6}$')
_BACKUP_RE = re.compile(r'^[A-Za-z0-9]{4}-?[A-Za-z0-9]{4}$')


class InvalidInput(SuspiciousOperation):
    """A request value did not match the expected schema."""


def _limit(name, default):
    return getattr(settings, name, default)


def _text(value, field, max_length, *, allow_blank=True, strip=False):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise InvalidInput(f'{field} must be text')
    if strip:
        value = value.strip()
    if len(value) > max_length:
        raise InvalidInput(f'{field} is too long')
    if _CONTROL_RE.search(value):
        raise InvalidInput(f'{field} contains control characters')
    if not allow_blank and not value:
        raise InvalidInput(f'{field} is required')
    return value


def text(value, field, max_length=500, *, allow_blank=True, strip=False):
    return _text(
        value, field, max_length,
        allow_blank=allow_blank, strip=strip,
    )


def search_query(value, field='q', max_length=200):
    """Free-text search: bounded length, no controls, blank allowed."""
    return _text(value, field, max_length, allow_blank=True, strip=True)


def choice(value, allowed, field, *, default=None, allow_blank=False):
    if value in (None, ''):
        if allow_blank:
            return ''
        if default is not None:
            return default
        raise InvalidInput(f'{field} is required')
    if value not in allowed:
        raise InvalidInput(f'{field} is not an allowed value')
    return value


def integer(value, field, *, minimum=None, maximum=None, default=None):
    if value in (None, ''):
        if default is not None:
            return default
        raise InvalidInput(f'{field} is required')
    if isinstance(value, bool):
        raise InvalidInput(f'{field} must be an integer')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InvalidInput(f'{field} must be an integer') from None
    if minimum is not None and number < minimum:
        raise InvalidInput(f'{field} is below the minimum')
    if maximum is not None and number > maximum:
        raise InvalidInput(f'{field} is above the maximum')
    return number


def positive_int(value, field, *, maximum=2_147_483_647):
    return integer(value, field, minimum=1, maximum=maximum)


def boolean(value, field, *, default=False):
    if value in (None, ''):
        return default
    if value in ('1', 'true', 'True', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'False', 'no', 'off'):
        return False
    raise InvalidInput(f'{field} must be a boolean')


def identifier(value, field, max_length=100):
    value = _text(value, field, max_length, allow_blank=False, strip=True)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise InvalidInput(f'{field} has an invalid format')
    return value


def string_list(values, field, *, allowed=None, max_items=500):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if len(values) > max_items:
        raise InvalidInput(f'{field} has too many values')
    cleaned = []
    for value in values:
        value = _text(value, field, 100, allow_blank=False, strip=True)
        if allowed is not None and value not in allowed:
            raise InvalidInput(f'{field} contains an invalid value')
        cleaned.append(value)
    return cleaned


def id_list(values, field, *, max_items=1000):
    if values is None:
        return []
    if isinstance(values, (str, int)):
        values = [values]
    if len(values) > max_items:
        raise InvalidInput(f'{field} has too many values')
    cleaned = []
    for value in values:
        cleaned.append(positive_int(value, field))
    return cleaned


def totp_code(value):
    value = _text(value, 'code', 6, allow_blank=False, strip=True)
    if not _TOTP_RE.fullmatch(value):
        raise InvalidInput('code must be six digits')
    return value


def backup_code(value):
    value = _text(value, 'code', 9, allow_blank=False, strip=True)
    if not _BACKUP_RE.fullmatch(value):
        raise InvalidInput('code must be a backup code')
    return value


def validate_request(request):
    """Validate the transport-level schema of an incoming request."""
    max_path = _limit('INPUT_MAX_PATH_LENGTH', 2048)
    if len(request.path) > max_path:
        raise InvalidInput('path is too long')

    query_string = request.META.get('QUERY_STRING', '')
    max_query = _limit('INPUT_MAX_QUERY_STRING_LENGTH', 4096)
    if len(query_string) > max_query:
        raise InvalidInput('query string is too long')

    params = request.GET
    max_params = _limit('INPUT_MAX_QUERY_PARAMS', 50)
    if len(params) > max_params:
        raise InvalidInput('too many query parameters')
    max_value = _limit('INPUT_MAX_QUERY_VALUE_LENGTH', 1000)
    for key in params:
        if not _QUERY_KEY_RE.fullmatch(key):
            raise InvalidInput('invalid query parameter name')
        for value in params.getlist(key):
            _text(value, key, max_value, allow_blank=True)

    if request.method not in ('POST', 'PUT', 'PATCH'):
        return

    content_length = int(request.META.get('CONTENT_LENGTH') or 0)
    if not content_length:
        return

    content_type = (request.content_type or '').lower()
    if content_type not in (
        'application/x-www-form-urlencoded',
        'multipart/form-data',
    ):
        raise InvalidInput('unsupported content type')

    max_fields = _limit('INPUT_MAX_FORM_FIELDS', 2000)
    max_field_value = _limit('INPUT_MAX_FORM_VALUE_LENGTH', 100_000)
    post = request.POST
    if len(post) > max_fields:
        raise InvalidInput('too many form fields')
    for key in post:
        if not _FORM_KEY_RE.fullmatch(key):
            raise InvalidInput('invalid form field name')
        for value in post.getlist(key):
            _text(value, key, max_field_value, allow_blank=True)

    max_files = _limit('DATA_UPLOAD_MAX_NUMBER_FILES', 20)
    if len(request.FILES) > max_files:
        raise InvalidInput('too many uploaded files')
    max_filename = _limit('INPUT_MAX_FILENAME_LENGTH', 255)
    for uploaded in request.FILES.values():
        name = uploaded.name or ''
        if len(name) > max_filename or _CONTROL_RE.search(name):
            raise InvalidInput('invalid uploaded filename')
