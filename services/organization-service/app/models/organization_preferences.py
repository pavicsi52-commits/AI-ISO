"""``organization_preferences`` table.

Per docs/033's "Organization Preferences" objective bullet -- distinct
from :class:`~app.models.organization_settings.OrganizationSettings`
(security/policy configuration) the same way
``services/user-management-service``'s ``UserPreferences`` is distinct
from its ``UserSettings``: softer, UI-facing defaults rather than
security policy.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class OrganizationPreferences(BaseModel):
    """One organization's UI/dashboard/notification preference defaults."""

    __tablename__ = "organization_preferences"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", name="uq_organization_preferences_org"),
    )

    dashboard_layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ui_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["OrganizationPreferences"]
