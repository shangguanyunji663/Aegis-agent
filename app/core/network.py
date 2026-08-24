"""Outbound HTTP URL validation shared by server-side integrations."""
from __future__ import annotations

import ipaddress
import socket
import urllib.request
from collections.abc import Callable
from urllib.parse import ParseResult, urlparse

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost."})
_ALLOWED_SCHEMES = frozenset({"http", "https"})
UrlOpener = Callable[..., object]


def validate_public_http_url(value: str) -> ParseResult:
    """Validate an outbound URL and all addresses returned by DNS.

    The check intentionally rejects localhost, loopback, private, link-local,
    reserved, unspecified, multicast, and other non-global destinations.
    Call this immediately before every server-side request to reduce DNS
    rebinding exposure; the redirect handler below repeats it for redirects.
    """
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not hostname:
        raise ValueError("outbound URL must use http or https and include a host")
    if parsed.username or parsed.password:
        raise ValueError("outbound URL must not include credentials")
    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError("localhost is not an allowed outbound host")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    if literal is not None:
        addresses.add(literal)
    else:
        try:
            infos = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ValueError(f"outbound host cannot be resolved: {hostname}") from exc
        for info in infos:
            try:
                addresses.add(ipaddress.ip_address(info[4][0]))
            except ValueError as exc:
                raise ValueError(f"outbound host returned an invalid address: {hostname}") from exc

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError(f"outbound host resolves to a private or reserved address: {hostname}")
    return parsed


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject a redirect unless its destination passes the same URL gate."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(request: urllib.request.Request, timeout: float):
    """Open a request after validating its URL and every HTTP redirect."""
    validate_public_http_url(request.full_url)
    opener = urllib.request.build_opener(_ValidatedRedirectHandler())
    return opener.open(request, timeout=timeout)
