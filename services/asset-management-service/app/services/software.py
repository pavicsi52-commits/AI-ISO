"""Software inventory and patch tracking. Per docs/038 "SOFTWARE
MANAGEMENT" "Track": Installed Software, Versions, Licenses, Patches,
Security Updates, End-of-Life Status, Software Inventory.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.asset_patch_history import AssetPatchHistoryEntry
from app.models.asset_software import AssetSoftware
from app.models.enums import AuditOutcome, SoftwareEndOfLifeStatus
from app.repositories.asset_patch_history import AssetPatchHistoryRepository
from app.repositories.asset_software import AssetSoftwareRepository


class SoftwareService:
    """Manages installed software and its patch history for a managed asset."""

    def __init__(
        self, software: AssetSoftwareRepository, patch_history: AssetPatchHistoryRepository
    ) -> None:
        self._software = software
        self._patch_history = patch_history

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetSoftware]:
        """Every installed software item on *managed_asset_id* ("Software Inventory")."""
        return await self._software.list_for_managed_asset(managed_asset_id)

    async def install(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        name: str,
        software_version: str | None,
        license_key: str | None,
        end_of_life_status: SoftwareEndOfLifeStatus,
        installed_at: datetime | None,
    ) -> AssetSoftware:
        """Record an installed software item ("Installed Software"/"Licenses")."""
        return await self._software.create(
            AssetSoftware(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                name=name,
                software_version=software_version,
                license_key=license_key,
                end_of_life_status=end_of_life_status,
                installed_at=installed_at,
            )
        )

    async def record_patch(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        software_id: UUID | None,
        patch_name: str,
        applied_at: datetime,
        outcome: AuditOutcome,
        notes: str | None,
    ) -> AssetPatchHistoryEntry:
        """Record an applied patch or security update ("Patches"/"Security Updates")."""
        return await self._patch_history.create(
            AssetPatchHistoryEntry(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                software_id=software_id,
                patch_name=patch_name,
                applied_at=applied_at,
                outcome=outcome,
                notes=notes,
            )
        )

    async def list_patch_history(self, managed_asset_id: UUID) -> list[AssetPatchHistoryEntry]:
        """Every patch/security update applied to *managed_asset_id*, newest first."""
        return await self._patch_history.list_for_managed_asset(managed_asset_id)


__all__ = ["SoftwareService"]
