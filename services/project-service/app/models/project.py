"""``projects`` table -- the project root entity.

Per docs/034 "PROJECT MODEL": Project ID, Organization ID, Name,
Display Name, Description, Code, Status, Owner, Visibility, Default
Language, Timezone, Category, Priority, Created At, Updated At,
Archived At, Metadata.

Every entity inheriting :class:`shared_core.database.base.BaseModel`
carries an inherited ``project_id`` column (nullable, per
:class:`shared_core.base.tenant_mixin.TenantMixin` -- "nullable for
organization-scoped entities"). This entity's own ``project_id`` is set
equal to its own ``id`` at creation (see
``app/services/project.py::ProjectService.create()``) -- the same
self-referential pattern ``services/organization-service`` established
for its own ``organization_id``, one tenant level down. Every child
table in this service overrides that same inherited column to
non-nullable and adds a real ``ForeignKeyConstraint`` back to
``projects.id`` (see e.g. ``app/models/project_settings.py``).

``organization_id`` (also inherited, mandatory) remains a bare,
foreign-key-less UUID -- this service's own database is physically
separate from ``services/organization-service``'s, so a cross-database
foreign key is not possible; this is the same "no cross-service FK"
convention every AI-IOS service other than organization-service itself
follows for organization references.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProjectPriority, ProjectStatus, ProjectVisibility


class Project(BaseModel):
    """One project. Its own ``project_id`` column equals its own ``id``."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ProjectStatus] = mapped_column(
        String(16), default=ProjectStatus.DRAFT, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    visibility: Mapped[ProjectVisibility] = mapped_column(
        String(16), default=ProjectVisibility.PRIVATE
    )
    default_language: Mapped[str] = mapped_column(String(16), default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    category: Mapped[str | None] = mapped_column(String(64), default=None)
    priority: Mapped[ProjectPriority] = mapped_column(String(16), default=ProjectPriority.MEDIUM)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["Project"]
