"""``certificate_store`` table. Per docs/035 "CERTIFICATE MANAGEMENT":
TLS Certificates, Client Certificates, CA Certificates, Certificate
Chains, Expiration Tracking, Renewal Hooks, Revocation, Import, Export.

The certificate itself (:attr:`certificate_pem`) is stored in
plaintext -- an X.509 certificate is a public document by design (its
whole purpose is to be handed to anyone who asks); only its *private
key*, if this service also holds one, is sensitive, and is stored as a
:class:`~app.models.secret.Secret` referenced by
:attr:`private_key_secret_id` rather than duplicated here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CertificateStatus, CertificateType


class Certificate(BaseModel):
    """One certificate's public material and validity metadata."""

    __tablename__ = "certificate_store"

    name: Mapped[str] = mapped_column(String(255))
    certificate_type: Mapped[CertificateType] = mapped_column(String(16), index=True)
    certificate_pem: Mapped[str] = mapped_column(Text)
    chain_pem: Mapped[list[str]] = mapped_column(JSON, default=list)
    private_key_secret_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="SET NULL"), default=None
    )
    subject: Mapped[str] = mapped_column(String(1024))
    issuer: Mapped[str] = mapped_column(String(1024))
    serial_number: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[CertificateStatus] = mapped_column(
        String(16), default=CertificateStatus.VALID, index=True
    )


__all__ = ["Certificate"]
