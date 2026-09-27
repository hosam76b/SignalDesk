"""Outbound URL validation (SSRF guard).

User-supplied URLs reach the server's network stack through several paths
(quick ingest, spider seeds, webhook targets, AI provider base URLs). Each of
those is a request-forgery primitive: ``http://169.254.169.254/`` reaches the
cloud metadata service, ``http://127.0.0.1:8000/`` reaches unauthenticated
endpoints on the very process issuing the request, and ``http://10.0.0.5/``
walks the internal network.

This module centralizes the policy so every caller applies the same rules:

* only ``http``/``https`` (kills ``file://``, ``ftp://``, ``gopher://``, ...)
* no credentials embedded in the authority
* the resolved address is checked against loopback, link-local, private,
  reserved, and multicast ranges -- pinning to the *resolved IP* is what makes
  this meaningful, because a public hostname can resolve to ``127.0.0.1``

DNS results are re-checked on every call rather than cached, so a DNS rebinding
answer cannot be replayed from a previous resolution. For the same reason this
is a best-effort control for high-assurance deployments: a hostile authoritative
server can still win the race between our resolve and httpx's connect. Closing
that fully requires a pinned-IP transport (see ``require_pinned_ip``).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Ports that are never a legitimate monitoring target but are extremely
#: useful to an attacker for pivoting to admin panels and databases.
BLOCKED_PORTS = frozenset({22, 23, 25, 445, 1433, 1521, 3306, 5432, 6379, 9200, 11211, 27017})


class UnsafeURLError(ValueError):
    """Raised when a URL is rejected by the SSRF policy."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a rejection reason for a blocked address, else None."""
    if ip.is_loopback:
        return "loopback address"
    if ip.is_link_local:
        # Covers 169.254.0.0/16, i.e. the cloud metadata endpoint, and
        # IPv6 fe80::/10.
        return "link-local address (includes cloud metadata endpoints)"
    if ip.is_private:
        return "private network address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_unspecified:
        return "unspecified address"
    # is_site_local exists on IPv6Address only, not on IPv4Address, so it has
    # to be probed rather than read directly.
    if getattr(ip, "is_site_local", False):
        return "site-local address"
    # Python 3.13 tightened is_global to also exclude CGNAT (100.64.0.0/10) and
    # other special-purpose blocks, which is the behaviour we want; on older
    # versions the is_private check above already covers the relevant ranges.
    if not getattr(ip, "is_global", True):
        return "non-global address"
    return None


def _resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to every address it maps to.

    Raises UnsafeURLError when resolution fails or yields nothing.
    """
    try:
        # getaddrinfo returns (family, ..., sockaddr); sockaddr[0] is the address.
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Host '{hostname}' could not be resolved") from exc
    except UnicodeError as exc:
        # A hostname that cannot even be IDNA-encoded is never legitimate.
        raise UnsafeURLError(f"Host '{hostname}' is not a valid hostname") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            addresses.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    if not addresses:
        raise UnsafeURLError(f"Host '{hostname}' resolved to no usable address")
    return addresses


def validate_url(
    url: str,
    *,
    allow_private: bool = False,
    allow_blocked_ports: bool = False,
    max_length: int = 2048,
) -> str:
    """Validate ``url`` against the SSRF policy and return it normalized.

    Args:
        url: The candidate URL.
        allow_private: Permit private/loopback/link-local targets. Only enable
            this for a deliberately self-hosted feed the operator controls.
        allow_blocked_ports: Permit the well-known administrative ports.
        max_length: Reject absurdly long URLs before doing any DNS work.

    Raises:
        UnsafeURLError: If the URL violates any rule.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("URL must be a non-empty string")

    candidate = url.strip()
    if len(candidate) > max_length:
        raise UnsafeURLError(f"URL exceeds the {max_length} character limit")

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeURLError(f"Malformed URL: {exc}") from exc

    scheme = (parts.scheme or "").lower()
    if not scheme:
        raise UnsafeURLError("URL must include a scheme (http or https)")
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"Scheme '{scheme}' is not allowed; only http and https are accepted"
        )

    if parts.username or parts.password:
        raise UnsafeURLError("URLs with embedded credentials are not allowed")

    try:
        hostname = parts.hostname
    except ValueError as exc:
        # urlsplit raises for malformed IPv6 literals such as [::1::2].
        raise UnsafeURLError(f"Malformed host in URL: {exc}") from exc
    if not hostname:
        raise UnsafeURLError("URL must include a hostname")
    hostname = hostname.strip().lower()

    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError(f"Invalid port in URL: {exc}") from exc
    if port is not None and not allow_blocked_ports and port in BLOCKED_PORTS:
        raise UnsafeURLError(f"Port {port} is not permitted for outbound requests")

    if allow_private:
        return candidate

    # An IP literal still has to pass the address policy; skip the DNS step.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        reason = _is_blocked_ip(literal)
        if reason:
            raise UnsafeURLError(
                f"Target {hostname} is blocked: it is a {reason}"
            )
        return candidate

    for address in _resolve(hostname):
        reason = _is_blocked_ip(address)
        if reason:
            raise UnsafeURLError(
                f"Host '{hostname}' resolves to {address}, which is blocked: "
                f"it is a {reason}"
            )
    return candidate


def validate_urls(
    urls: list[str],
    *,
    allow_private: bool = False,
    allow_blocked_ports: bool = False,
) -> list[str]:
    """Validate a list of URLs, raising on the first rejection."""
    return [
        validate_url(
            url,
            allow_private=allow_private,
            allow_blocked_ports=allow_blocked_ports,
        )
        for url in urls
    ]


def is_safe_url(url: str, **kwargs) -> bool:
    """Boolean form of :func:`validate_url` for call sites that only need a check."""
    try:
        validate_url(url, **kwargs)
    except UnsafeURLError:
        return False
    return True
