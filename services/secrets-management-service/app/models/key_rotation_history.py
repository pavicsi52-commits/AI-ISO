"""``key_rotation_history`` table -- rotation history for *encryption
keys* (DEKs/master key), distinct from
``app/models/secret_rotation.py`` (which tracks rotation of secrets'
own values). Per docs/035 "KEY MANAGEMENT": "Key Rotation", "Key
Versioning", "Key Revocation".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class KeyRotationHistoryEntry(BaseModel):
    """One encryption-key rotation event."""

    __tablename__ = "key_rotation_history"

    encryption_key_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("encryption_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("encryption_keys.id", ondelete="SET NULL"), default=None
    )
    rotated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)
    secrets_migrated_count: Mapped[int] = mapped_column(Integer, default=0)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["KeyRotationHistoryEntry"]
