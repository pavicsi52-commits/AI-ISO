"""Response schemas for GET/DELETE /auth/devices."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DeviceSummary(BaseModel):
    """One trusted/known device, as returned by ``GET /auth/devices``."""

    id: UUID
    device_name: str | None
    browser: str | None
    operating_system: str | None
    ip_address: str | None
    location: str | None
    last_login_at: datetime | None
    is_trusted: bool
    trusted_until: datetime | None


__all__ = ["DeviceSummary"]
