"""``user_preferences`` table.

Per docs/031 "USER PREFERENCES": Language, Theme, Timezone, Date
Format, Time Format, Dashboard Preferences, Notification Preferences,
Accessibility, Default Organization, Default Project.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class UserPreferences(BaseModel):
    """One user's platform preferences (as opposed to ``UserSettings``'
    application/security behavior toggles -- see that model's docstring
    for the distinction).
    """

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(16), default="en")
    theme: Mapped[str] = mapped_column(String(32), default="system")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    date_format: Mapped[str] = mapped_column(String(32), default="YYYY-MM-DD")
    time_format: Mapped[str] = mapped_column(String(16), default="24h")
    dashboard_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    accessibility: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    default_organization_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    default_project_id: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["UserPreferences"]
