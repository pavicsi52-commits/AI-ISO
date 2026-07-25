"""Execution targets. Per docs/040 "EXECUTION TARGETS"/"CONNECTOR INTEGRATION"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.automation_target import AutomationTarget
from app.models.enums import ConnectorType, ExecutionTargetType
from app.repositories.automation_target import AutomationTargetRepository


class AutomationTargetService:
    """Creates, reads, updates, and deletes automation execution targets."""

    def __init__(self, targets: AutomationTargetRepository) -> None:
        self._targets = targets

    async def get_by_id(self, target_id: UUID) -> AutomationTarget:
        """Return the target identified by *target_id*.

        Raises:
            NotFoundError: If no such target exists.
        """
        return await self._targets.require_by_id(target_id)

    async def list_for_org(
        self, organization_id: UUID, *, target_type: ExecutionTargetType | None = None
    ) -> list[AutomationTarget]:
        """Every target belonging to *organization_id*."""
        return await self._targets.list_for_org(organization_id, target_type=target_type)

    async def list_by_ids(self, target_ids: list[UUID]) -> list[AutomationTarget]:
        """Every target among *target_ids* that still exists and is active."""
        return await self._targets.list_by_ids(target_ids)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        target_type: ExecutionTargetType,
        connector_type: ConnectorType,
        address: str,
        port: int | None,
        username: str | None,
        credential_ref: str | None,
        inventory_asset_id: UUID | None,
        labels: dict[str, str],
        tags: list[str],
        metadata: dict[str, Any],
    ) -> AutomationTarget:
        """Register a new execution target."""
        return await self._targets.create(
            AutomationTarget(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                target_type=target_type,
                connector_type=connector_type,
                address=address,
                port=port,
                username=username,
                credential_ref=credential_ref,
                inventory_asset_id=inventory_asset_id,
                labels=labels,
                tags=tags,
                metadata_=metadata,
            )
        )

    async def delete(self, target_id: UUID) -> None:
        """Soft-delete an execution target."""
        await self._targets.delete(target_id)


__all__ = ["AutomationTargetService"]
