"""Real, native network collectors -- ``CONNECTIVITY``/``PORTS``/``DNS``/
``CERTIFICATES`` check types, run directly from this process rather
than delegated to another service, since a plain TCP connect, DNS
resolution, or TLS handshake needs no remote execution capability this
service doesn't already have via the stdlib.

Every collector reads the target host from
``ValidationTarget.target_metadata["host"]`` -- a target with no
``host`` recorded (e.g. a purely logical target like an automation job)
cannot be network-collected, and each function raises
``shared_core.exceptions.validation.ValidationError`` (this is a
caller-configuration problem, not an unreachable-dependency one)
rather than crashing the whole execution.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import time
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget


def _require_host(target: ValidationTarget) -> str:
    host = target.target_metadata.get("host")
    if not host:
        raise ValidationError(
            f"Target {target.id!r} has no 'host' in its own target_metadata; "
            "network collectors require one."
        )
    return str(host)


async def collect_connectivity(
    check: ValidationCheck, target: ValidationTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Open a TCP connection to the target's own host and measure latency."""
    host = _require_host(target)
    port = int(check.parameters.get("port", 443))
    started = time.monotonic()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=check.timeout_seconds
        )
    except (TimeoutError, OSError) as exc:
        return {"reachable": False, "error": str(exc)}
    writer.close()
    await writer.wait_closed()
    return {"reachable": True, "latency_ms": (time.monotonic() - started) * 1000}


async def collect_port(
    check: ValidationCheck, target: ValidationTarget, context: CollectorContext
) -> dict[str, Any]:
    """Check whether the target's own configured port accepts connections."""
    return await collect_connectivity(check, target, context)


async def collect_dns(
    check: ValidationCheck, target: ValidationTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Resolve the target's own host and report whether resolution succeeded."""
    host = _require_host(target)
    loop = asyncio.get_running_loop()
    try:
        addresses = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyname_ex, host),
            timeout=check.timeout_seconds,
        )
    except (TimeoutError, OSError) as exc:
        return {"resolved": False, "error": str(exc)}
    return {"resolved": True, "addresses": addresses[2]}


async def collect_certificate(
    check: ValidationCheck, target: ValidationTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Fetch the target's own TLS certificate and report its expiry.

    Deliberately does not verify the certificate chain
    (``check_hostname=False``/``verify_mode=ssl.CERT_NONE``) -- this
    check's own job is reading *when the presented certificate itself
    expires*, not judging whether it chains to a public CA, since many
    real internal enterprise targets legitimately present a
    private-CA or self-signed certificate. ``getpeercert()`` (the
    parsed-dict form) returns an empty result whenever verification is
    disabled, so the raw DER bytes are parsed directly with
    ``cryptography.x509`` instead.
    """
    host = _require_host(target)
    port = int(check.parameters.get("port", 443))
    context_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context_ssl.check_hostname = False
    context_ssl.verify_mode = ssl.CERT_NONE
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context_ssl, server_hostname=host),
            timeout=check.timeout_seconds,
        )
    except (TimeoutError, OSError, ssl.SSLError) as exc:
        return {"valid": False, "error": str(exc)}
    ssl_object = writer.get_extra_info("ssl_object")
    der_cert = ssl_object.getpeercert(binary_form=True) if ssl_object is not None else None
    writer.close()
    await writer.wait_closed()
    if not der_cert:
        return {"valid": False, "error": "no certificate presented"}
    certificate = x509.load_der_x509_certificate(der_cert)
    not_after = certificate.not_valid_after_utc
    days_remaining = (not_after - datetime.now(UTC)).days
    return {"valid": True, "not_after": not_after.isoformat(), "days_remaining": days_remaining}


__all__ = ["collect_certificate", "collect_connectivity", "collect_dns", "collect_port"]
