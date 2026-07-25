"""``user_credentials`` table.

Per docs/030 "DATABASE TABLES"/"PASSWORD POLICY": Argon2 Hashing.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CredentialType


class UserCredential(BaseModel):
    """One credential (currently always a password) belonging to a user."""

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    credential_type: Mapped[CredentialType] = mapped_column(
        String(32), default=CredentialType.PASSWORD
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), default=None)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["UserCredential"]
