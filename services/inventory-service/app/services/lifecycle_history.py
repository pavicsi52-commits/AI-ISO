"""Asset lifecycle transition history. Used internally by
:class:`~app.services.asset.AssetService`; has no REST surface of its
own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.asset_lifecycle_history import AssetLifecycleHistoryEntry
from app.models.enums import LifecycleState
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository


class AssetLifecycleHistoryService:
    """Records and lists lifecycle transitions for an asset."""

    def __init__(self, history: AssetLifecycleHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        previous_state: LifecycleState | None,
        new_state: LifecycleState,
        transitioned_by: UUID | None,
        notes: str | None = None,
    ) -> AssetLifecycleHistoryEntry:
        """Record one lifecycle-state transition."""
        return await self._history.create(
            AssetLifecycleHistoryEntry(
                asset_id=asset_id,
                organization_id=organization_id,
                previous_state=previous_state,
                new_state=new_state,
                transitioned_by=transitioned_by,
                notes=notes,
                transitioned_at=datetime.now(UTC),
            )
        )

    async def list_for_asset(self, asset_id: UUID) -> list[AssetLifecycleHistoryEntry]:
        """Every lifecycle transition for *asset_id*, newest first."""
        return await self._history.list_for_asset(asset_id)


__all__ = ["AssetLifecycleHistoryService"]
