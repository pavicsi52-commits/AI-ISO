"""``user_metadata`` table.

A normalized, auditable key/value store for admin-defined custom
fields -- distinct from ``users.metadata`` (a small JSONB blob for
quick, non-audited data) and ``user_profiles.custom_fields`` (a
profile-specific JSONB blob): this table exists so each key/value pair
can be individually created/updated/deleted and audited (docs/031
"AUDIT": "Metadata Updates" is called out as its own audited
operation, which a single JSONB blob column can't express at that
granularity).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserMetadataEntry(BaseModel):
    """One (user_id, key) -> value custom metadata entry."""

    __tablename__ = "user_metadata"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_metadata_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["UserMetadataEntry"]
