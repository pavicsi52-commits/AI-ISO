"""``project_notes`` table -- free-form collaborative notes on a project."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ProjectNote(BaseModel):
    """One free-form note attached to a project."""

    __tablename__ = "project_notes"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    author_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    content: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["ProjectNote"]
