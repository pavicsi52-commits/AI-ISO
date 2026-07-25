"""Asset health check history. Used internally by
:class:`~app.services.asset.AssetService`; has no REST surface of its
own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.asset_health_history import AssetHealthHistoryEntry
from app.models.enums import HealthStatus
from app.repositories.asset_health_history import AssetHealthHistoryRepository


class AssetHealthHistoryService:
    """Records and lists health check results for an asset."""

    def __init__(self, history: AssetHealthHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        health_status: HealthStatus,
        detail: str | None = None,
    ) -> AssetHealthHistoryEntry:
        """Record one health check result."""
        return await self._history.create(
            AssetHealthHistoryEntry(
                asset_id=asset_id,
                organization_id=organization_id,
                health_status=health_status,
                detail=detail,
                checked_at=datetime.now(UTC),
            )
        )

    async def list_for_asset(self, asset_id: UUID) -> list[AssetHealthHistoryEntry]:
        """Every health check result for *asset_id*, newest first."""
        return await self._history.list_for_asset(asset_id)


__all__ = ["AssetHealthHistoryService"]
