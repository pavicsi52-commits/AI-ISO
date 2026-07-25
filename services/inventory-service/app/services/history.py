"""Asset narrative timeline. Distinct from the status/health/lifecycle
history services (which each track one specific concern) and from
``inventory_audit`` (privileged-action audit trail) -- this is a
human-readable feed of notable events, the same
"narrative feed vs. audit trail" split
``services/project-service``'s own ``project_activity``/``project_audit``
pair established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.asset_history import AssetHistoryEntry
from app.repositories.asset_history import AssetHistoryRepository


class AssetHistoryService:
    """Records and lists narrative timeline entries for an asset."""

    def __init__(self, history: AssetHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> AssetHistoryEntry:
        """Record one narrative timeline entry."""
        return await self._history.create(
            AssetHistoryEntry(
                asset_id=asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                event_type=event_type,
                detail=detail or {},
            )
        )

    async def list_for_asset(self, asset_id: UUID) -> list[AssetHistoryEntry]:
        """Every narrative timeline entry for *asset_id*, newest first."""
        return await self._history.list_for_asset(asset_id)


__all__ = ["AssetHistoryService"]
