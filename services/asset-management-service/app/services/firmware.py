"""Firmware tracking. Per docs/038 "FIRMWARE MANAGEMENT" "Track":
Firmware Version, Available Updates, Upgrade History, Rollback
History, Firmware Compliance, Vendor Recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.asset_firmware import AssetFirmware
from app.models.enums import ComplianceStatus
from app.repositories.asset_firmware import AssetFirmwareRepository
from app.services.lifecycle import LifecycleService


class FirmwareService:
    """Tracks a managed asset's current firmware state."""

    def __init__(self, firmware: AssetFirmwareRepository, lifecycle: LifecycleService) -> None:
        self._firmware = firmware
        self._lifecycle = lifecycle

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetFirmware | None:
        """Return *managed_asset_id*'s current firmware state, or ``None``."""
        return await self._firmware.get_for_managed_asset(managed_asset_id)

    async def upsert(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        current_version: str,
        available_version: str | None,
        compliance_status: ComplianceStatus,
        vendor_recommendation: str | None,
    ) -> AssetFirmware:
        """Record *managed_asset_id*'s current firmware state, recording an
        "Upgrade History"/"Rollback History" entry whenever the version
        actually changes.
        """
        existing = await self.get_for_managed_asset(managed_asset_id)
        if existing is None:
            record = await self._firmware.create(
                AssetFirmware(
                    managed_asset_id=managed_asset_id,
                    organization_id=organization_id,
                    current_version=current_version,
                    available_version=available_version,
                    compliance_status=compliance_status,
                    vendor_recommendation=vendor_recommendation,
                    last_checked_at=datetime.now(UTC),
                )
            )
            await self._lifecycle.record_change(
                managed_asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                event_type="firmware_installed",
                detail={"to": current_version},
            )
            return record

        previous_version = existing.current_version
        existing.current_version = current_version
        existing.available_version = available_version
        existing.compliance_status = compliance_status
        existing.vendor_recommendation = vendor_recommendation
        existing.last_checked_at = datetime.now(UTC)

        if previous_version != current_version:
            event_type = (
                "firmware_upgraded"
                if current_version > previous_version
                else "firmware_rolled_back"
            )
            await self._lifecycle.record_change(
                managed_asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                event_type=event_type,
                detail={"from": previous_version, "to": current_version},
            )
        return existing


__all__ = ["FirmwareService"]
