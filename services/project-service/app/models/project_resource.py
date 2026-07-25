"""``project_resources`` table. Per docs/034 "PROJECT RESOURCES": tracks
every infrastructure resource, inventory asset, workflow, automation
job, connector, AI agent, report, dashboard, etc. a project owns --
each row is a link to an entity owned by another AI-IOS service, never
a copy of its data. ``resource_id`` is a bare UUID with no foreign key,
the same cross-service-safe convention every prior AI-IOS service
established for references to entities outside their own database.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProjectResourceType


class ProjectResource(BaseModel):
    """One external resource linked to a project."""

    __tablename__ = "project_resources"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "resource_type", "resource_id", name="uq_project_resource_link"
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    resource_type: Mapped[ProjectResourceType] = mapped_column(String(32), index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    linked_by: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["ProjectResource"]
