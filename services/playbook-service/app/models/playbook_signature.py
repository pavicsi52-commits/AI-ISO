"""``playbook_signatures`` table. Per docs/041 "SECURITY" "Support":
Digital Signatures, Checksum Validation, Publisher Verification,
Content Integrity, Signature Verification.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SignatureAlgorithm


class PlaybookSignature(BaseModel):
    """One digital signature over a playbook version's own content checksum."""

    __tablename__ = "playbook_signatures"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbook_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signer_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    algorithm: Mapped[SignatureAlgorithm] = mapped_column(
        String(16), default=SignatureAlgorithm.ED25519
    )
    public_key_fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    signature: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["PlaybookSignature"]
