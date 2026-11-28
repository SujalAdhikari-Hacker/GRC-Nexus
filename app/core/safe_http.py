"""SSRF-resistant outbound HTTP.

Threat-intelligence and vulnerability enrichment fetch remote JSON/text. Those
URLs are currently constants, but a future feed setting or a compromised DNS
record must not be able to turn the worker into a proxy for
``169.254.169.254``, ``127.0.0.1`` or an internal RFC1918 service.

The helpers below enforce four rules:

* only ``https`` URLs without embedded credentials;
* the hostname must be on the configured allowlist;
* every resolved address must be globally routable: IPv4-mapped IPv6 is
  unwrapped and judged as IPv4, and CGNAT, loopback, private, link-local,
  multicast, reserved and documentation ranges are refused;
* redirects are refused, and response bodies are size-capped.

For the strongest guarantee, run the worker behind an egress proxy that
enforces the same allowlist at the network layer.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from django.conf import settings

DEFAULT_ALLOWED_HOSTS = frozenset({
    'raw.githubusercontent.com',
    'otx.alienvault.com',
    'threatcluster.io',
    'threatfox-api.abuse.ch',
    'services.nvd.nist.gov',
    'api.first.org',
    'www.cisa.gov',
    'cisa.gov',
})

_BLOCKED_SUFFIXES = (
    '.local', '.localhost', '.internal', '.home', '.lan', '.corp',
    '.intranet', '.private',
)


class UnsafeURL(ValueError):
    """Raised when an outbound URL could reach a non-public destination."""


def _allowed_hosts():
    configured = getattr(settings, 'SAFE_HTTP_ALLOWED_HOSTS', None)
    if configured:
        return frozenset(h.strip().lower() for h in configured if h.strip())
    return DEFAULT_ALLOWED_HOSTS


def _is_public(address):
    """True only for a globally routable unicast address.

    IPv4-mapped IPv6 (``::ffff:10.0.0.1``) is unwrapped and judged by its IPv4
    address, so a mapped private address cannot slip through. ``is_global``
    also catches shared CGNAT space (``100.64.0.0/10``) and documentation
    ranges that the narrower ``is_private`` flag lets through.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_url(url, *, allowed_hosts=None):
    """Validate ``url`` and return it unchanged, or raise :class:`UnsafeURL`."""
    parsed = urlparse((url or '').strip())
    if parsed.scheme.lower() != 'https':
        raise UnsafeURL('Only https URLs are allowed.')
    if not parsed.hostname:
        raise UnsafeURL('URL has no hostname.')
    if parsed.username or parsed.password:
        raise UnsafeURL('URLs with embedded credentials are not allowed.')

    host = parsed.hostname.rstrip('.').lower()
    if host in ('localhost', 'localhost.localdomain') or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURL('Internal hostnames are not allowed.')

    allowlist = frozenset(allowed_hosts) if allowed_hosts is not None else _allowed_hosts()
    if host not in allowlist:
        raise UnsafeURL(f'Host {host!r} is not on the outbound allowlist.')

    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeURL('URL has an invalid port.') from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL(f'Could not resolve {host!r}.') from exc
    if not infos:
        raise UnsafeURL(f'Could not resolve {host!r}.')

    for info in infos:
        if not _is_public(info[4][0]):
            raise UnsafeURL(f'{host!r} resolves to a non-public address.')
    return url


def _read_limited(response, max_bytes):
    declared = response.headers.get('Content-Length')
    if declared:
        try:
            if int(declared) > max_bytes:
                raise UnsafeURL('Response is larger than the allowed limit.')
        except ValueError:
            pass

    chunks = []
    total = 0
    for chunk in response.iter_content(64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise UnsafeURL('Response is larger than the allowed limit.')
        chunks.append(chunk)
    return b''.join(chunks)


def safe_request(
    method,
    url,
    *,
    params=None,
    data=None,
    json=None,
    headers=None,
    timeout=None,
    max_bytes=None,
    allowed_hosts=None,
):
    """Perform a non-redirecting, allowlisted, size-capped HTTP request."""
    validate_url(url, allowed_hosts=allowed_hosts)
    timeout = timeout or getattr(settings, 'SAFE_HTTP_TIMEOUT', 20)
    max_bytes = max_bytes or getattr(settings, 'SAFE_HTTP_MAX_BYTES', 25 * 1024 * 1024)

    response = requests.request(
        method.upper(),
        url,
        params=params,
        data=data,
        json=json,
        headers=headers,
        timeout=timeout,
        allow_redirects=False,
        stream=True,
    )
    try:
        if 300 <= response.status_code < 400:
            raise UnsafeURL('Redirects are not followed for outbound requests.')
        body = _read_limited(response, max_bytes)
    finally:
        response.close()

    response._content = body
    response._content_consumed = True
    return response


def safe_get(url, **kwargs):
    return safe_request('GET', url, **kwargs)


def safe_post(url, **kwargs):
    return safe_request('POST', url, **kwargs)
