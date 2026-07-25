"""Tests for :mod:`app.certificates.importer`, cross-checked against
``shared_core.security.certificates`` (already tested at that layer;
here we assert the higher-level ``ParsedCertificate`` extraction).
"""

from __future__ import annotations

import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.certificates.importer import parse_certificate_pem
from app.models.enums import CertificateStatus


def _make_self_signed_cert(*, not_before: datetime.datetime, not_after: datetime.datetime) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.aiios.local")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def test_parse_certificate_pem_extracts_metadata() -> None:
    now = datetime.datetime.now(datetime.UTC)
    pem = _make_self_signed_cert(
        not_before=now - datetime.timedelta(days=1), not_after=now + datetime.timedelta(days=365)
    )
    parsed = parse_certificate_pem(pem)
    assert parsed.subject == "CN=test.aiios.local"
    assert parsed.issuer == "CN=test.aiios.local"
    assert parsed.status == CertificateStatus.VALID
    assert len(parsed.fingerprint) == 64  # SHA-256 hex digest
    assert parsed.serial_number.isdigit()


def test_parse_certificate_pem_marks_expired_certificate() -> None:
    now = datetime.datetime.now(datetime.UTC)
    pem = _make_self_signed_cert(
        not_before=now - datetime.timedelta(days=730), not_after=now - datetime.timedelta(days=1)
    )
    parsed = parse_certificate_pem(pem)
    assert parsed.status == CertificateStatus.EXPIRED


def test_parse_certificate_pem_marks_not_yet_valid_as_valid() -> None:
    """Per the module's own documented simplification: a not-yet-valid
    certificate reports VALID (it becomes current once its start date
    arrives), since CertificateStatus has no dedicated third state.
    """
    now = datetime.datetime.now(datetime.UTC)
    pem = _make_self_signed_cert(
        not_before=now + datetime.timedelta(days=1), not_after=now + datetime.timedelta(days=365)
    )
    parsed = parse_certificate_pem(pem)
    assert parsed.status == CertificateStatus.VALID


def test_parse_certificate_pem_rejects_malformed_input() -> None:
    with pytest.raises(ValueError):
        parse_certificate_pem("not a certificate")


def test_different_certificates_have_different_fingerprints() -> None:
    now = datetime.datetime.now(datetime.UTC)
    pem_1 = _make_self_signed_cert(not_before=now, not_after=now + datetime.timedelta(days=1))
    pem_2 = _make_self_signed_cert(not_before=now, not_after=now + datetime.timedelta(days=1))
    assert parse_certificate_pem(pem_1).fingerprint != parse_certificate_pem(pem_2).fingerprint
