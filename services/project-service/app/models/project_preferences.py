"""``project_preferences`` table -- per-project UI/dashboard preferences,
mirroring ``services/organization-service``'s identical
``OrganizationPreferences`` shape at one tenant level down. See
``app/models/project_settings.py``'s docstring for the ``project_id``
override rationale.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class ProjectPreferences(BaseModel):
    """One project's UI/dashboard/notification display preferences."""

    __tablename__ = "project_preferences"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_preferences_project"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    dashboard_layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ui_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ProjectPreferences"]
