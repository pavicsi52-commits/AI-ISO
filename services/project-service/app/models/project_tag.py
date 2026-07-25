"""``project_tags`` table -- free-form tags assigned to a project,
mirroring ``services/organization-service``'s identical
``OrganizationTag`` shape. Per docs/034 "PROJECT TAGS": Custom Tags,
Categories.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectTag(BaseModel):
    """One tag assigned to a project."""

    __tablename__ = "project_tags"
    __table_args__ = (UniqueConstraint("project_id", "label", name="uq_project_tag_label"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["ProjectTag"]
