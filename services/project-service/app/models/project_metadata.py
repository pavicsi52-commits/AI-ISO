"""``project_metadata`` table -- per-project custom key/value metadata,
mirroring ``services/organization-service``'s identical
``OrganizationMetadataEntry`` shape at one tenant level down.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectMetadataEntry(BaseModel):
    """One custom key/value metadata entry on a project."""

    __tablename__ = "project_metadata"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_project_metadata_key"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["ProjectMetadataEntry"]
