"""Discovery job narrative timeline. Distinct from ``discovery_audit``
(privileged-action audit trail) -- the same "narrative feed vs. audit
trail" split ``services/inventory-service``'s own ``asset_history``/
``inventory_audit`` pair established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.discovery_history import DiscoveryHistoryEntry
from app.repositories.discovery_history import DiscoveryHistoryRepository


class DiscoveryHistoryService:
    """Records and lists narrative timeline entries for a discovery job."""

    def __init__(self, history: DiscoveryHistoryRepository) -> None:
        self._history = history

    async def record(
        self,
        job_id: UUID,
        *,
        organization_id: UUID,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> DiscoveryHistoryEntry:
        """Record one narrative timeline entry."""
        return await self._history.create(
            DiscoveryHistoryEntry(
                job_id=job_id,
                organization_id=organization_id,
                event_type=event_type,
                detail=detail or {},
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryHistoryEntry]:
        """Every narrative timeline entry for *job_id*, newest first."""
        return await self._history.list_for_job(job_id)


__all__ = ["DiscoveryHistoryService"]
