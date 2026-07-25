"""``user_avatars`` table.

Per docs/031 "AVATAR MANAGEMENT": Upload, Replace, Delete, Resize,
Thumbnail, Storage Integration, Validation, Virus Scan Hook. The
*current* avatar is denormalized onto ``users.avatar`` (the storage key
of the active image, for fast reads); this table is the full upload
history -- every avatar ever uploaded, active or replaced -- since
"Replace" implies the old one is tracked, not silently discarded.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class UserAvatar(BaseModel):
    """One uploaded avatar image, current or superseded."""

    __tablename__ = "user_avatars"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(1024))
    thumbnail_key: Mapped[str | None] = mapped_column(String(1024), default=None)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    virus_scan_passed: Mapped[bool | None] = mapped_column(Boolean, default=None)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["UserAvatar"]
