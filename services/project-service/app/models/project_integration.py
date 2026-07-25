"""``project_integrations`` table -- external system integrations
configured for a project (e.g. a connector or third-party system
reference), distinct from :class:`~app.models.project_resource
.ProjectResource`'s generic resource-linking in that an integration
carries its own enable/disable state and configuration payload.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectIntegration(BaseModel):
    """One external-system integration configured for a project."""

    __tablename__ = "project_integrations"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_integration_name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    integration_type: Mapped[str] = mapped_column(String(64))
    external_reference_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ProjectIntegration"]
