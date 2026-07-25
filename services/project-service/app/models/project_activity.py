"""``project_activity`` table -- a narrative feed of what happened on a
project, mirroring ``services/organization-service``'s identical
``OrganizationActivityEntry`` shape. Per docs/034 "EVENTS": the same
list backs both event publication and this human-readable feed.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProjectActivityType


class ProjectActivity(BaseModel):
    """One narrative activity-feed entry for a project."""

    __tablename__ = "project_activity"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    activity_type: Mapped[ProjectActivityType] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ProjectActivity"]
