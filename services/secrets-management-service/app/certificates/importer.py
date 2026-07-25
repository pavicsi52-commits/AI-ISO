"""Certificate import: parses PEM certificates into the fields needed to
populate ``certificate_store`` rows. Per docs/035 "CERTIFICATE
MANAGEMENT": Import, Expiration Tracking.

Thin orchestration on top of ``shared_core.security.certificates`` --
issuance/signing is out of scope there too; this only extracts metadata
from a certificate the caller already has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shared_core.security.certificates import (
    get_certificate_fingerprint,
    is_certificate_expired,
    parse_certificate,
)

from app.models.enums import CertificateStatus


@dataclass(frozen=True, slots=True)
class ParsedCertificate:
    """Metadata extracted from a PEM certificate."""

    subject: str
    issuer: str
    serial_number: str
    fingerprint: str
    not_before: datetime
    not_after: datetime
    status: CertificateStatus


def parse_certificate_pem(certificate_pem: str) -> ParsedCertificate:
    """Parse *certificate_pem* into the metadata a ``certificate_store``
    row needs.

    :attr:`~ParsedCertificate.status` reflects whether the certificate
    has passed its expiration time only -- a not-yet-valid certificate is
    reported ``VALID`` here (it becomes genuinely current once its start
    date arrives), since :class:`~app.models.enums.CertificateStatus` has
    no dedicated "not yet valid" state.

    Raises:
        ValueError: If *certificate_pem* isn't a well-formed PEM certificate.
    """
    certificate = parse_certificate(certificate_pem)
    status = (
        CertificateStatus.EXPIRED
        if is_certificate_expired(certificate)
        else CertificateStatus.VALID
    )
    return ParsedCertificate(
        subject=certificate.subject.rfc4514_string(),
        issuer=certificate.issuer.rfc4514_string(),
        serial_number=str(certificate.serial_number),
        fingerprint=get_certificate_fingerprint(certificate),
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
        status=status,
    )


__all__ = ["ParsedCertificate", "parse_certificate_pem"]
