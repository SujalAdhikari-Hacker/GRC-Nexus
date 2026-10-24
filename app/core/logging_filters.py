"""Log redaction.

Django itself does not log request bodies, but application code occasionally
logs exception strings, URLs or third-party responses that can contain a
password, API key or bearer token. This filter is attached to every console
handler so those values are masked before they reach the container log.
"""
import re

_REDACTED = '[REDACTED]'

_KEY_VALUE = re.compile(
    r'(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|auth[_-]?key|'
    r'authorization|csrfmiddlewaretoken|sessionid|set-cookie|cookie)'
    r'(\s*[:=]\s*)((?:bearer\s+)?[^\s,;]+)'
)
_BEARER = re.compile(r'(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+')
_COOKIE_HEADER = re.compile(r'(?i)(set-cookie:\s*)[^\n]+')


def redact(value):
    """Return ``value`` with credential-looking fragments masked."""
    text = str(value)
    text = _KEY_VALUE.sub(lambda m: f'{m.group(1)}{m.group(2)}{_REDACTED}', text)
    text = _BEARER.sub(lambda m: f'{m.group(1)}{_REDACTED}', text)
    text = _COOKIE_HEADER.sub(lambda m: f'{m.group(1)}{_REDACTED}', text)
    return text


class SensitiveDataFilter:
    """Logging filter that redacts credentials from every record."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            # Never let a malformed log record take down the request.
            return True
        record.msg = redact(message)
        record.args = ()
        return True
