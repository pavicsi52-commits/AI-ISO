"""Request/response schemas for ``/certificates``. Per docs/035
"CERTIFICATE MANAGEMENT": Import, Expiration Tracking.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CertificateStatus, CertificateType


class CertificateImportRequest(BaseModel):
    """Body of ``POST /certificates``.

    :attr:`private_key` is optional PEM material for the certificate's
    private key -- when present it's stored as a
    :class:`~app.models.secret.Secret` and :attr:`owner_id` becomes that
    secret's owner; when absent, only the (public) certificate is
    imported.
    """

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    certificate_type: CertificateType
    certificate_pem: str = Field(min_length=1)
    chain_pem: list[str] = Field(default_factory=list)
    private_key: str | None = None
    owner_id: UUID | None = None


class CertificateResponse(BaseModel):
    """One certificate's public material and validity metadata."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    certificate_type: CertificateType
    certificate_pem: str
    chain_pem: list[str]
    private_key_secret_id: UUID | None
    subject: str
    issuer: str
    serial_number: str
    fingerprint: str
    not_before: datetime
    not_after: datetime
    status: CertificateStatus
    created_at: datetime
    updated_at: datetime


__all__ = ["CertificateImportRequest", "CertificateResponse"]
