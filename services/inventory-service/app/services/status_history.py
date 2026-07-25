"""Asset status transition history. Used internally by
:class:`~app.services.asset.AssetService`; has no REST surface of its
own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.asset_status_history import AssetStatusHistoryEntry
from app.models.enums import AssetStatus
from app.repositories.asset_status_history import AssetStatusHistoryRepository


class AssetStatusHistoryService:
    """Records and lists status transitions for an asset."""

    def __init__(self, history: AssetStatusHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        previous_status: AssetStatus | None,
        new_status: AssetStatus,
        changed_by: UUID | None,
        reason: str | None = None,
    ) -> AssetStatusHistoryEntry:
        """Record one status transition."""
        return await self._history.create(
            AssetStatusHistoryEntry(
                asset_id=asset_id,
                organization_id=organization_id,
                previous_status=previous_status,
                new_status=new_status,
                changed_by=changed_by,
                reason=reason,
                changed_at=datetime.now(UTC),
            )
        )

    async def list_for_asset(self, asset_id: UUID) -> list[AssetStatusHistoryEntry]:
        """Every status transition for *asset_id*, newest first."""
        return await self._history.list_for_asset(asset_id)


__all__ = ["AssetStatusHistoryService"]
