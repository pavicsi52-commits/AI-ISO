"""Response schemas for GET/DELETE /auth/sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionSummary(BaseModel):
    """One session, as returned by ``GET /auth/sessions``."""

    id: UUID
    session_id: str
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    is_current: bool = False


__all__ = ["SessionSummary"]
