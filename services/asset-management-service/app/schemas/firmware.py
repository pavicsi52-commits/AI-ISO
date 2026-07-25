"""Response schema for :class:`~app.models.asset_firmware.AssetFirmware`
-- surfaced as part of a managed asset's technical profile rather than
through its own top-level REST resource, per docs/038's own REST APIs
list (which names no dedicated firmware path).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ComplianceStatus


class AssetFirmwareResponse(BaseModel):
    """One managed asset's current firmware state."""

    id: UUID
    managed_asset_id: UUID
    current_version: str
    available_version: str | None
    compliance_status: ComplianceStatus
    vendor_recommendation: str | None
    last_checked_at: datetime | None


__all__ = ["AssetFirmwareResponse"]
