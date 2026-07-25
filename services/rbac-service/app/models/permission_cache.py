"""``permission_cache`` table -- a durable snapshot of a computed
effective-permission matrix.

Per docs/032 "CACHING": "User Permission Matrix", "Integrate with
Prompt 019." The hot lookup path is Redis
(:mod:`app.cache.authorization_cache`, wrapping
``shared_core.cache.manager.CacheManager`` per that integration note);
this table is the durable, queryable record of what was last computed
for a subject, so a cache eviction or a cold Redis doesn't require
recomputing from scratch on every request, and so "what permissions
did this user actually have at time X" survives a cache flush.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class PermissionCacheEntry(BaseModel):
    """The last computed effective-permission set for one user/scope."""

    __tablename__ = "permission_cache"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "project_id", name="uq_permission_cache"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    permissions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["PermissionCacheEntry"]
