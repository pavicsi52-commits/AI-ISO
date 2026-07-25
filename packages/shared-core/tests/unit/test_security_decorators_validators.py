"""Tests for the new security decorators (requires_auth/api_key/mfa) and validators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from shared_core.exceptions import AuthenticationError
from shared_core.security.context import bind_security_context, reset_security_context
from shared_core.security.decorators import requires_api_key, requires_auth, requires_mfa
from shared_core.security.validators import (
    validate_certificate_not_expired,
    validate_certificate_pem,
    validate_required_security_headers,
)


def _build_valid_cert_pem() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.local")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


# --- decorators/ ---


@pytest.fixture(autouse=True)
def _reset_security() -> None:
    reset_security_context()
    yield
    reset_security_context()


async def test_requires_auth_allows_when_user_id_bound() -> None:
    bind_security_context(user_id=uuid4())

    @requires_auth()
    async def handler() -> str:
        return "ok"

    assert await handler() == "ok"


async def test_requires_auth_denies_when_unauthenticated() -> None:
    @requires_auth()
    async def handler() -> str:
        return "ok"

    with pytest.raises(AuthenticationError):
        await handler()


async def test_requires_api_key_allows_for_api_key_auth() -> None:
    bind_security_context(user_id=uuid4(), auth_method="api_key")

    @requires_api_key()
    async def handler() -> str:
        return "ok"

    assert await handler() == "ok"


async def test_requires_api_key_denies_for_jwt_auth() -> None:
    bind_security_context(user_id=uuid4(), auth_method="jwt")

    @requires_api_key()
    async def handler() -> str:
        return "ok"

    with pytest.raises(AuthenticationError):
        await handler()


async def test_requires_mfa_allows_when_verified() -> None:
    bind_security_context(user_id=uuid4(), mfa_verified=True)

    @requires_mfa()
    async def handler() -> str:
        return "ok"

    assert await handler() == "ok"


async def test_requires_mfa_denies_when_not_verified() -> None:
    bind_security_context(user_id=uuid4(), mfa_verified=False)

    @requires_mfa()
    async def handler() -> str:
        return "ok"

    with pytest.raises(AuthenticationError):
        await handler()


# --- validators/ ---


def test_validate_certificate_pem_true_for_well_formed_cert() -> None:
    pem = _build_valid_cert_pem()

    assert validate_certificate_pem(pem) is True
    assert validate_certificate_not_expired(pem) is True


def test_validate_certificate_pem_false_for_garbage() -> None:
    assert validate_certificate_pem("not a certificate") is False


def test_validate_certificate_not_expired_false_for_garbage() -> None:
    assert validate_certificate_not_expired("not a certificate") is False


def test_validate_required_security_headers_true_when_present() -> None:
    result = validate_required_security_headers(
        {"X-Frame-Options": "DENY", "Content-Type": "application/json"},
        required=("x-frame-options",),
    )

    assert result is True


def test_validate_required_security_headers_false_when_missing() -> None:
    result = validate_required_security_headers(
        {"Content-Type": "application/json"}, required=("x-frame-options",)
    )

    assert result is False
