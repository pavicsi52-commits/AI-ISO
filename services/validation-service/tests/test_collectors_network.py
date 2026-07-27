"""Tests for :mod:`app.collectors.network` -- real TCP/DNS/TLS
collectors, run against a genuine local server this test starts
itself (never a live external host, the same "no live external
dependency" discipline every prior AI-IOS service's own network-facing
tests established).
"""

from __future__ import annotations

import asyncio
import datetime
import ipaddress
import ssl
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from shared_core.exceptions.validation import ValidationError

from app.collectors.network import (
    collect_certificate,
    collect_connectivity,
    collect_dns,
    collect_port,
)
from app.models.enums import ValidationCheckType, ValidationTargetType
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget


def _check(
    check_type: ValidationCheckType, *, parameters: dict[str, object] | None = None
) -> ValidationCheck:
    return ValidationCheck(
        organization_id=uuid.uuid4(),
        check_type=check_type,
        name="test-check",
        collector_key="test",
        parameters=parameters or {},
        timeout_seconds=2.0,
    )


def _target(*, host: str | None = "127.0.0.1") -> ValidationTarget:
    return ValidationTarget(
        organization_id=uuid.uuid4(),
        target_type=ValidationTargetType.PHYSICAL_SERVER,
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
        check = _check(ValidationCheckType.CONNECTIVITY, parameters={"port": tcp_server})
        data = await collect_connectivity(check, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is True
        assert data["latency_ms"] >= 0

    async def test_unreachable_port_reports_false(self) -> None:
        check = _check(ValidationCheckType.CONNECTIVITY, parameters={"port": 1})
        data = await collect_connectivity(check, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is False
        assert "error" in data

    async def test_missing_host_raises(self) -> None:
        check = _check(ValidationCheckType.CONNECTIVITY, parameters={"port": 443})
        with pytest.raises(ValidationError, match="host"):
            await collect_connectivity(check, _target(host=None), None)  # type: ignore[arg-type]


class TestCollectPort:
    async def test_delegates_to_connectivity(self, tcp_server: int) -> None:
        check = _check(ValidationCheckType.PORTS, parameters={"port": tcp_server})
        data = await collect_port(check, _target(), None)  # type: ignore[arg-type]
        assert data["reachable"] is True


class TestCollectDns:
    async def test_resolves_localhost(self) -> None:
        check = _check(ValidationCheckType.DNS)
        data = await collect_dns(check, _target(host="localhost"), None)  # type: ignore[arg-type]
        assert data["resolved"] is True
        assert data["addresses"]

    async def test_unresolvable_host_reports_false(self) -> None:
        check = _check(ValidationCheckType.DNS)
        data = await collect_dns(
            check, _target(host="this-host-does-not-exist.invalid"), None  # type: ignore[arg-type]
        )
        assert data["resolved"] is False


class TestCollectCertificate:
    async def test_valid_certificate_reports_expiry(self, tls_server: int) -> None:
        check = _check(ValidationCheckType.CERTIFICATES, parameters={"port": tls_server})
        data = await collect_certificate(check, _target(), None)  # type: ignore[arg-type]
        assert data["valid"] is True
        assert data["days_remaining"] > 0

    async def test_unreachable_port_reports_invalid(self) -> None:
        check = _check(ValidationCheckType.CERTIFICATES, parameters={"port": 1})
        data = await collect_certificate(check, _target(), None)  # type: ignore[arg-type]
        assert data["valid"] is False
