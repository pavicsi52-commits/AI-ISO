"""Response schemas for ``GET /users/activity``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ActivityType


class ActivityEntryResponse(BaseModel):
    """One recorded activity event."""

    id: UUID
    activity_type: ActivityType
    description: str | None
    detail: dict[str, Any]
    created_at: datetime


__all__ = ["ActivityEntryResponse"]
