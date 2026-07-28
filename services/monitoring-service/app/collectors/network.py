"""Real, native network collectors -- TCP connectivity/port, DNS, TLS
certificate expiry, and HTTP/API checks, run directly from this process
rather than delegated to another service, since none of these need a
remote execution capability this service doesn't already have via the
stdlib/``httpx``. Matches ``services/validation-service``'s own
:mod:`app.collectors.network`, adapted to
:class:`~app.models.monitoring_collector.MonitoringCollector`/
:class:`~app.models.monitoring_target.MonitoringTarget`.

The actual probing logic lives in the private, model-agnostic
``_tcp_connect``/``_resolve_dns``/``_fetch_certificate``/``_http_request``
helpers, each taking only the raw values it needs -- both the
:class:`~app.models.monitoring_collector.MonitoringCollector`-facing
wrappers below (registered under
:mod:`app.collectors.registry` for recurring metric collection) and
:mod:`app.collectors.synthetic`'s own
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`-
facing wrappers (one-off scheduled probes) call the same helpers rather
than duplicating the probing logic once per owning model.

Every collector reads the target host from
``MonitoringTarget.target_metadata["host"]`` -- a target with no
``host`` recorded (e.g. a purely logical target) cannot be
network-collected, and each function raises
``shared_core.exceptions.validation.ValidationError`` (a
caller-configuration problem, not an unreachable-dependency one)
rather than crashing the whole collection run.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography import x509
from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget

DEFAULT_TIMEOUT_SECONDS = 10.0


def require_host(target: MonitoringTarget) -> str:
    """Return *target*'s own configured host.

    Raises:
        ValidationError: If *target* has no ``host`` in its own ``target_metadata``.
    """
    host = target.target_metadata.get("host")
    if not host:
        raise ValidationError(
            f"Target {target.id!r} has no 'host' in its own target_metadata; "
            "network collectors require one."
        )
    return str(host)


async def _tcp_connect(host: str, port: int, *, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout_seconds
        )
    except (TimeoutError, OSError) as exc:
        return {"reachable": False, "error": str(exc)}
    writer.close()
    await writer.wait_closed()
    return {"reachable": True, "latency_ms": (time.monotonic() - started) * 1000}


async def _resolve_dns(host: str, *, timeout_seconds: float) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    try:
        addresses = await asyncio.wait_for(
            loop.run_in_executor(None, socket.gethostbyname_ex, host), timeout=timeout_seconds
        )
    except (TimeoutError, OSError) as exc:
        return {"resolved": False, "error": str(exc)}
    return {"resolved": True, "addresses": addresses[2]}


async def _fetch_certificate(host: str, port: int, *, timeout_seconds: float) -> dict[str, Any]:
    """Fetch *host*:*port*'s own presented TLS certificate and report its expiry.

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
    context_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context_ssl.check_hostname = False
    context_ssl.verify_mode = ssl.CERT_NONE
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context_ssl, server_hostname=host),
            timeout=timeout_seconds,
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


async def _http_request(
    url: str,
    *,
    method: str,
    timeout_seconds: float,
    expected_status: int,
    body_contains: str | None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.request(method, url)
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc)}
    latency_ms = (time.monotonic() - started) * 1000
    body_ok = body_contains is None or body_contains in response.text
    return {
        "reachable": True,
        "status_code": response.status_code,
        "status_matches": response.status_code == expected_status,
        "body_matches": body_ok,
        "latency_ms": latency_ms,
    }


async def collect_connectivity(
    collector: MonitoringCollector, target: MonitoringTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Open a TCP connection to the target's own host and measure latency."""
    host = require_host(target)
    port = int(collector.parameters.get("port", 443))
    timeout_seconds = float(collector.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    return await _tcp_connect(host, port, timeout_seconds=timeout_seconds)


async def collect_port(
    collector: MonitoringCollector, target: MonitoringTarget, context: CollectorContext
) -> dict[str, Any]:
    """Check whether the target's own configured port accepts connections."""
    return await collect_connectivity(collector, target, context)


async def collect_dns(
    collector: MonitoringCollector, target: MonitoringTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Resolve the target's own host and report whether resolution succeeded."""
    host = require_host(target)
    timeout_seconds = float(collector.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    return await _resolve_dns(host, timeout_seconds=timeout_seconds)


async def collect_certificate(
    collector: MonitoringCollector, target: MonitoringTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Fetch the target's own TLS certificate and report its expiry."""
    host = require_host(target)
    port = int(collector.parameters.get("port", 443))
    timeout_seconds = float(collector.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    return await _fetch_certificate(host, port, timeout_seconds=timeout_seconds)


async def collect_http(
    collector: MonitoringCollector, target: MonitoringTarget, _context: CollectorContext
) -> dict[str, Any]:
    """Issue a live HTTP request against the target's own configured URL
    and report status code, latency, and an optional body substring
    match ("HTTP Checks"/"API Checks").

    Raises:
        ValidationError: If *collector* has no ``url`` in its own ``parameters``.
    """
    url = collector.parameters.get("url")
    if not url:
        raise ValidationError(
            f"Collector {collector.id!r} (collector_key {collector.collector_key!r}) has no "
            "'url' in its own parameters; HTTP collectors require one."
        )
    del target
    return await _http_request(
        str(url),
        method=str(collector.parameters.get("method", "GET")).upper(),
        timeout_seconds=float(collector.parameters.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        expected_status=int(collector.parameters.get("expected_status", 200)),
        body_contains=collector.parameters.get("body_contains"),
    )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "collect_certificate",
    "collect_connectivity",
    "collect_dns",
    "collect_http",
    "collect_port",
    "require_host",
]
