"""``secret_rotation`` table -- rotation history for a secret's own
value. Per docs/035 "SECRET ROTATION": Manual, Scheduled, Automatic
Rotation, Rotation History, Failure Recovery.

Distinct from ``app/models/key_rotation_history.py``, which tracks
rotation of the *encryption keys* protecting secrets, not the secrets'
own values.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RotationOutcome, RotationTrigger


class SecretRotationEntry(BaseModel):
    """One rotation attempt for a secret."""

    __tablename__ = "secret_rotation"

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rotated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    trigger: Mapped[RotationTrigger] = mapped_column(String(16))
    previous_version_number: Mapped[int] = mapped_column(Integer)
    new_version_number: Mapped[int | None] = mapped_column(Integer, default=None)
    outcome: Mapped[RotationOutcome] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(String(2048), default=None)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["SecretRotationEntry"]
