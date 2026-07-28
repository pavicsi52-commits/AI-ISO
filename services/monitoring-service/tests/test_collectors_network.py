"""Tests for :mod:`app.collectors.network` -- real TCP/DNS/TLS/HTTP
collectors, run against a genuine local server this test starts itself
(never a live external host, the same "no live external dependency"
discipline ``services/validation-service``'s own network-facing tests
established).
"""

from __future__ import annotations

import asyncio
import datetime
import ipaddress
import ssl
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pytest_httpx import HTTPXMock
from shared_core.exceptions.validation import ValidationError

from app.collectors.network import (
    collect_certificate,
    collect_connectivity,
    collect_dns,
    collect_http,
    collect_port,
)
from app.models.enums import MonitoringTargetType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget


def _collector(*, parameters: dict[str, object] | None = None) -> MonitoringCollector:
    return MonitoringCollector(
        organization_id=uuid.uuid4(),
        name="test-collector",
        collector_key="test",
        parameters=parameters or {},
    )


def _target(*, host: str | None = "127.0.0.1") -> MonitoringTarget:
    return MonitoringTarget(
        organization_id=uuid.uuid4(),
        target_type=MonitoringTargetType.PHYSICAL_SERVER,
        external_id=str(uuid.uuid4()),
        name="test-target",
        target_metadata={"host": host} if host else {},
    )


@pytest.fixture
async def tcp_server() -> AsyncIterator[int]:
    """A genuine local TCP server accepting and immediately closing connections."""

    async def _handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port


def _self_signed_cert() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


@pytest.fixture
async def tls_server(tmp_path: Path) -> AsyncIterator[int]:
    """A genuine local TLS server presenting a real, freshly-generated self-signed certificate."""
    key_pem, cert_pem = _self_signed_cert()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    await asyncio.to_thread(cert_path.write_bytes, cert_pem)
    await asyncio.to_thread(key_path.write_bytes, key_pem)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)

    async def _handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port


class TestCollectConnectivity:
    async def test_reachable_host_reports_latency(self, tcp_server: int) -> None:
        collector = _collector(parameters={"port": tcp_server})
        data = await collect_connectivity(collector, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is True
        assert data["latency_ms"] >= 0

    async def test_unreachable_port_reports_false(self) -> None:
        collector = _collector(parameters={"port": 1})
        data = await collect_connectivity(collector, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is False
        assert "error" in data

    async def test_missing_host_raises(self) -> None:
        collector = _collector(parameters={"port": 443})
        with pytest.raises(ValidationError, match="host"):
            await collect_connectivity(collector, _target(host=None), None)  # type: ignore[arg-type]


class TestCollectPort:
    async def test_delegates_to_connectivity(self, tcp_server: int) -> None:
        collector = _collector(parameters={"port": tcp_server})
        data = await collect_port(collector, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is True


class TestCollectDns:
    async def test_resolves_localhost(self) -> None:
        collector = _collector()
        data = await collect_dns(collector, _target(host="localhost"), None)  # type: ignore[arg-type]
        assert data["resolved"] is True
        assert data["addresses"]

    async def test_unresolvable_host_reports_false(self) -> None:
        collector = _collector()
        data = await collect_dns(
            collector, _target(host="this-host-does-not-exist.invalid"), None  # type: ignore[arg-type]
        )
        assert data["resolved"] is False


class TestCollectCertificate:
    async def test_valid_certificate_reports_expiry(self, tls_server: int) -> None:
        collector = _collector(parameters={"port": tls_server})
        data = await collect_certificate(collector, _target(), None)  # type: ignore[arg-type]
        assert data["valid"] is True
        assert data["days_remaining"] > 0

    async def test_unreachable_port_reports_invalid(self) -> None:
        collector = _collector(parameters={"port": 1})
        data = await collect_certificate(collector, _target(), None)  # type: ignore[arg-type]
        assert data["valid"] is False


class TestCollectHttp:
    async def test_successful_request_reports_status(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="http://example.internal/health", json={"ok": True})
        collector = _collector(parameters={"url": "http://example.internal/health"})
        data = await collect_http(collector, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is True
        assert data["status_code"] == 200
        assert data["status_matches"] is True

    async def test_body_contains_check(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="http://example.internal/health", text="status: ok")
        collector = _collector(
            parameters={"url": "http://example.internal/health", "body_contains": "status: ok"}
        )
        data = await collect_http(collector, _target(), None)  # type: ignore[arg-type]
        assert data["body_matches"] is True

    async def test_unexpected_status_reports_mismatch(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(url="http://example.internal/health", status_code=503)
        collector = _collector(parameters={"url": "http://example.internal/health"})
        data = await collect_http(collector, _target(), None)  # type: ignore[arg-type]
        assert data["status_matches"] is False

    async def test_unreachable_reports_false(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        collector = _collector(parameters={"url": "http://example.internal/health"})
        data = await collect_http(collector, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is False

    async def test_missing_url_raises(self) -> None:
        collector = _collector()
        with pytest.raises(ValidationError, match="url"):
            await collect_http(collector, _target(), None)  # type: ignore[arg-type]
