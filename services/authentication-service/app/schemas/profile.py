"""Response schema for GET /auth/profile."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    """The authenticated caller's own profile."""

    id: UUID
    email: str
    display_name: str | None
    is_email_verified: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


__all__ = ["ProfileResponse"]
