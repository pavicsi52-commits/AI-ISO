"""``project_favorites`` table -- a user "starring" a project for quick access."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectFavorite(BaseModel):
    """One user's favorite-project marker."""

    __tablename__ = "project_favorites"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_favorite"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)


__all__ = ["ProjectFavorite"]
