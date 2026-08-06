"""``webhook_signatures`` -- an endpoint's own signing secrets, encrypted at rest."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SecretStatus, SignatureAlgorithm


class WebhookSignature(BaseModel):
    """``webhook_signatures`` -- one endpoint's own signing secret, at one version.

    ``secret_ciphertext`` is the output of :func:`shared_core.security
    .encryption.encrypt` -- never the raw secret. Rotation creates a new
    row (``version`` incremented) rather than overwriting the old one,
    so an in-flight delivery signed under the previous secret still
    verifies during the overlap window before the old row's own
    ``status`` moves to ``EXPIRED``.
    """

    __tablename__ = "webhook_signatures"
    __table_args__ = (
        Index("ix_webhook_signature_endpoint_version", "endpoint_id", "version", unique=True),
    )

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    algorithm: Mapped[SignatureAlgorithm] = mapped_column(
        String(16), default=SignatureAlgorithm.HMAC_SHA256
    )
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    status: Mapped[SecretStatus] = mapped_column(String(16), default=SecretStatus.ACTIVE, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["WebhookSignature"]
