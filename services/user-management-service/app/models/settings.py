"""``user_settings`` table.

Per docs/031 "USER SETTINGS": Display Settings, Privacy, Security
Preferences, Default Views, Shortcuts, Favorites, Feature Flags.
Distinct from ``UserPreferences``: preferences are "how the platform
should look and communicate with this user" (locale-ish, cosmetic);
settings are "how this user's own workspace behaves" (privacy,
security posture, saved views) -- matching docs/031's own split into
two separate sections and two separate tables.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class UserSettings(BaseModel):
    """One user's application behavior settings."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    display_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    privacy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    security_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    default_views: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    shortcuts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    favorites: Mapped[list[str]] = mapped_column(JSON, default=list)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["UserSettings"]
