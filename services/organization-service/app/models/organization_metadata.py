"""``organization_metadata`` table -- custom key/value metadata per organization."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationMetadataEntry(BaseModel):
    """One custom key/value metadata entry for an organization."""

    __tablename__ = "organization_metadata"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", "key", name="uq_organization_metadata_key"),
    )

    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["OrganizationMetadataEntry"]
