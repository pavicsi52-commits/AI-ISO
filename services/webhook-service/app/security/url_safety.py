"""Outgoing-URL safety (docs/057 "SECURITY": "Protection against SSRF").

`shared_core.validators.fields.web.validate_url` only checks scheme and
a non-empty netloc -- it has no concept of a *private-network*
destination, and `shared_core.validators.fields.network` has no
IP-range classification either. A genuine gap: an outgoing webhook
endpoint is a caller-supplied URL that this service's own workers will
repeatedly connect to, which is exactly the classic SSRF vector (a
caller registers ``http://169.254.169.254/latest/meta-data`` or
``http://10.0.0.5:6379`` and turns this service into a probe against
its own private network).

**Resolution-time, not just registration-time.** A hostname that
resolves to a public IP at endpoint-registration time can be
re-pointed at a private one later (DNS rebinding) -- so this module's
authoritative check validates the IPs a hostname *actually* resolves to
right before each delivery attempt, not only once at registration. The
registration-time check exists purely so an obviously-unsafe URL is
rejected immediately with a clear error, not silently accepted and only
failing (or worse, succeeding against an internal host) on first
delivery.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from shared_core.exceptions.validation import ValidationError

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def validate_scheme(url: str) -> None:
    """Reject any URL not using ``http``/``https``.

    Raises:
        ValidationError: If the scheme is missing or not http/https.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValidationError(f"Webhook endpoint URL must be http or https, got {scheme!r}.")


def is_public_address(ip: str) -> bool:
    """Whether *ip* is a genuinely public, routable address.

    Rejects private, loopback, link-local, multicast, reserved, and
    unspecified ranges -- everything ``ipaddress`` itself flags as not
    globally reachable, for both IPv4 and IPv6.
    """
    address = ipaddress.ip_address(ip)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def resolve_hostname(hostname: str) -> list[str]:
    """Every IP address *hostname* currently resolves to.

    Runs on the running event loop's own resolver
    (:meth:`asyncio.AbstractEventLoop.getaddrinfo`), which offloads the
    blocking ``getaddrinfo(3)`` syscall to a worker thread -- calling
    :func:`socket.getaddrinfo` directly here would block the whole
    event loop for the duration of a DNS lookup.

    Raises:
        ValidationError: If the hostname cannot be resolved at all.
    """
    try:
        results = await asyncio.get_running_loop().getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValidationError(
            f"Could not resolve webhook endpoint host {hostname!r}: {exc}"
        ) from exc
    return sorted({str(result[4][0]) for result in results})


async def assert_safe_url(url: str) -> None:
    """Reject *url* if its scheme is unsafe or it resolves to any non-public address.

    Raises:
        ValidationError: If the scheme is not http/https, the host
            cannot be resolved, or any resolved address is private,
            loopback, link-local, multicast, reserved, or unspecified.
    """
    validate_scheme(url)
    hostname = urlparse(url).hostname
    if not hostname:
        raise ValidationError("Webhook endpoint URL has no host.")
    for ip in await resolve_hostname(hostname):
        if not is_public_address(ip):
            raise ValidationError(
                f"Webhook endpoint host {hostname!r} resolves to a non-public address "
                f"({ip}) -- refusing to prevent server-side request forgery."
            )


__all__ = ["assert_safe_url", "is_public_address", "resolve_hostname", "validate_scheme"]
