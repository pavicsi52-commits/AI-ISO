"""Tests for certificate parsing, validation, and expiration checking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from shared_core.security.certificates import (
    days_until_expiration,
    get_certificate_fingerprint,
    is_certificate_expired,
    is_certificate_not_yet_valid,
    is_certificate_valid_now,
    is_self_signed,
    parse_certificate,
)


def _build_self_signed_cert_pem(
    *, not_before: datetime, not_after: datetime, common_name: str = "test.aiios.local"
) -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(private_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


@pytest.fixture
def valid_cert_pem() -> str:
    now = datetime.now(UTC)
    return _build_self_signed_cert_pem(
        not_before=now - timedelta(days=1), not_after=now + timedelta(days=365)
    )


@pytest.fixture
def expired_cert_pem() -> str:
    now = datetime.now(UTC)
    return _build_self_signed_cert_pem(
        not_before=now - timedelta(days=730), not_after=now - timedelta(days=365)
    )


@pytest.fixture
def not_yet_valid_cert_pem() -> str:
    now = datetime.now(UTC)
    return _build_self_signed_cert_pem(
        not_before=now + timedelta(days=1), not_after=now + timedelta(days=365)
    )


def test_parse_certificate_returns_a_certificate(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert isinstance(certificate, x509.Certificate)


def test_parse_certificate_raises_for_malformed_pem() -> None:
    with pytest.raises(ValueError):
        parse_certificate("not a real certificate")


def test_is_certificate_expired_false_for_valid_cert(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert is_certificate_expired(certificate) is False


def test_is_certificate_expired_true_for_expired_cert(expired_cert_pem: str) -> None:
    certificate = parse_certificate(expired_cert_pem)

    assert is_certificate_expired(certificate) is True


def test_is_certificate_not_yet_valid_true_for_future_cert(not_yet_valid_cert_pem: str) -> None:
    certificate = parse_certificate(not_yet_valid_cert_pem)

    assert is_certificate_not_yet_valid(certificate) is True


def test_is_certificate_not_yet_valid_false_for_active_cert(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert is_certificate_not_yet_valid(certificate) is False


def test_is_certificate_valid_now_true_for_active_cert(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert is_certificate_valid_now(certificate) is True


def test_is_certificate_valid_now_false_for_expired_cert(expired_cert_pem: str) -> None:
    certificate = parse_certificate(expired_cert_pem)

    assert is_certificate_valid_now(certificate) is False


def test_is_certificate_valid_now_false_for_future_cert(not_yet_valid_cert_pem: str) -> None:
    certificate = parse_certificate(not_yet_valid_cert_pem)

    assert is_certificate_valid_now(certificate) is False


def test_days_until_expiration_positive_for_valid_cert(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert days_until_expiration(certificate) > 300


def test_days_until_expiration_negative_for_expired_cert(expired_cert_pem: str) -> None:
    certificate = parse_certificate(expired_cert_pem)

    assert days_until_expiration(certificate) < 0


def test_is_self_signed_true_for_self_signed_cert(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    assert is_self_signed(certificate) is True


def test_get_certificate_fingerprint_is_stable(valid_cert_pem: str) -> None:
    certificate = parse_certificate(valid_cert_pem)

    fingerprint_a = get_certificate_fingerprint(certificate)
    fingerprint_b = get_certificate_fingerprint(certificate)

    assert fingerprint_a == fingerprint_b
    assert len(fingerprint_a) == 64  # SHA-256 hex digest
