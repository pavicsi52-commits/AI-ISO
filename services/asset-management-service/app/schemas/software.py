"""Response schemas for :class:`~app.models.asset_software.AssetSoftware`
and :class:`~app.models.asset_patch_history.AssetPatchHistoryEntry`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AuditOutcome, SoftwareEndOfLifeStatus


class AssetSoftwareResponse(BaseModel):
    """One installed software item."""

    id: UUID
    managed_asset_id: UUID
    name: str
    software_version: str | None
    license_key: str | None
    end_of_life_status: SoftwareEndOfLifeStatus
    installed_at: datetime | None


class AssetPatchHistoryResponse(BaseModel):
    """One applied patch/security update."""

    id: UUID
    managed_asset_id: UUID
    software_id: UUID | None
    patch_name: str
    applied_at: datetime
    outcome: AuditOutcome
    notes: str | None


__all__ = ["AssetPatchHistoryResponse", "AssetSoftwareResponse"]
