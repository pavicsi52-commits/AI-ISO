"""Certificate parsing, validation, and expiration checking.

Per docs/017_Enterprise_Security_Framework.md.txt "CERTIFICATES":
Certificate Validation, Certificate Expiration, Certificate Rotation,
Self-Signed Support, CA Support. No certificate *issuance* happens here
(that requires a CA, out of scope for a framework) -- only parsing and
checking properties of certificates a service already has.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes


def parse_certificate(pem_data: str) -> x509.Certificate:
    """Parse a PEM-encoded X.509 certificate.

    Raises:
        ValueError: If *pem_data* isn't a well-formed PEM certificate.
    """
    return x509.load_pem_x509_certificate(pem_data.encode("ascii"))


def is_certificate_expired(certificate: x509.Certificate, *, now: datetime | None = None) -> bool:
    """Return whether *certificate* has passed its expiration time."""
    return (now or datetime.now(UTC)) >= certificate.not_valid_after_utc


def is_certificate_not_yet_valid(
    certificate: x509.Certificate, *, now: datetime | None = None
) -> bool:
    """Return whether *certificate*'s validity period hasn't started yet."""
    return (now or datetime.now(UTC)) < certificate.not_valid_before_utc


def is_certificate_valid_now(certificate: x509.Certificate, *, now: datetime | None = None) -> bool:
    """Return whether *certificate* is currently within its validity window."""
    current = now or datetime.now(UTC)
    expired = is_certificate_expired(certificate, now=current)
    not_yet_valid = is_certificate_not_yet_valid(certificate, now=current)
    return not expired and not not_yet_valid


def days_until_expiration(certificate: x509.Certificate, *, now: datetime | None = None) -> int:
    """Days remaining until *certificate* expires (negative if already expired)."""
    return (certificate.not_valid_after_utc - (now or datetime.now(UTC))).days


def is_self_signed(certificate: x509.Certificate) -> bool:
    """Return whether *certificate*'s issuer and subject are identical."""
    return certificate.issuer == certificate.subject


def get_certificate_fingerprint(certificate: x509.Certificate) -> str:
    """Return the SHA-256 fingerprint of *certificate*, hex-encoded."""
    return certificate.fingerprint(hashes.SHA256()).hex()
