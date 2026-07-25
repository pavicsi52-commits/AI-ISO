"""``secret_metadata`` table -- per-secret custom key/value metadata,
mirroring every prior AI-IOS service's identical metadata-entry shape.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class SecretMetadataEntry(BaseModel):
    """One custom key/value metadata entry on a secret."""

    __tablename__ = "secret_metadata"
    __table_args__ = (UniqueConstraint("secret_id", "key", name="uq_secret_metadata_key"),)

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["SecretMetadataEntry"]
