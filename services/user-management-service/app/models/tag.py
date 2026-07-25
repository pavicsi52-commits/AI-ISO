"""``user_tags`` table.

Per docs/031 "USER TAGS": Labels, Groups, Categories, Custom Tags,
Search, Filtering. docs/031's "DATABASE TABLES" names a single
``user_tags`` table (not a normalized ``tags`` catalog plus a join
table), so one row *is* one tag assignment -- searchable/filterable by
``label``/``category`` directly, per
:class:`shared_core.database.filtering.FilterOperator`.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UserTag(BaseModel):
    """One tag/label assigned to a user."""

    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_user_tags_user_label"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["UserTag"]
