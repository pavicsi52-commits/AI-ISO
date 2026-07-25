"""``organization_tags`` table -- simple tagging for organizations."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationTag(BaseModel):
    """One tag assigned to an organization."""

    __tablename__ = "organization_tags"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", "label", name="uq_organization_tag_label"),
    )

    label: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["OrganizationTag"]
