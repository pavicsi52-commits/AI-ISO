"""Monitoring target registration and lookup. :meth:`get_or_create`
reuses the same row across repeated collections of the same real asset
rather than registering a fresh duplicate every time, matching
``services/validation-service``'s own
:class:`app.services.target.ValidationTargetService`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import MonitoringTargetType
from app.models.monitoring_target import MonitoringTarget
from app.repositories.monitoring_target import MonitoringTargetRepository


class MonitoringTargetService:
    """Registers and reads monitoring targets."""

    def __init__(self, targets: MonitoringTargetRepository) -> None:
        self._targets = targets

    async def get_by_id(self, target_id: UUID) -> MonitoringTarget:
        """Return the target identified by *target_id*.

        Raises:
            NotFoundError: If no such target exists.
        """
        return await self._targets.require_by_id(target_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringTarget]:
        """Every monitoring target belonging to *organization_id*."""
        return await self._targets.list_for_org(organization_id)

    async def list_by_ids(self, target_ids: list[UUID]) -> list[MonitoringTarget]:
        """Resolve a list of target ids into their actual rows."""
        return await self._targets.list_by_ids(target_ids)

    async def get_or_create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        target_type: MonitoringTargetType,
        external_id: str,
        name: str,
        target_metadata: dict[str, Any],
    ) -> MonitoringTarget:
        """Reuse the target already registered for this external asset, or
        register a new one.
        """
        existing = await self._targets.get_by_external_id(organization_id, target_type, external_id)
        if existing is not None:
            existing.name = name
            existing.target_metadata = target_metadata
            return await self._targets.update(existing)
        return await self._targets.create(
            MonitoringTarget(
                organization_id=organization_id,
                project_id=project_id,
                target_type=target_type,
                external_id=external_id,
                name=name,
                target_metadata=target_metadata,
            )
        )


__all__ = ["MonitoringTargetService"]
