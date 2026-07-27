"""Validation target resolution. Per docs/043's own "VALIDATION
TARGETS" -- targets are resolved dynamically at execute time from a
caller-supplied :class:`~app.schemas.target.TargetReference`, never
pre-registered through a CRUD form of their own (see
``app/schemas/target.py``'s own docstring for why).
:meth:`get_or_create` reuses the same row across repeated executions of
the same real asset rather than registering a fresh duplicate every
time.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import ValidationTargetType
from app.models.validation_target import ValidationTarget
from app.repositories.validation_target import ValidationTargetRepository


class ValidationTargetService:
    """Resolves and reads validation targets."""

    def __init__(self, targets: ValidationTargetRepository) -> None:
        self._targets = targets

    async def get_by_id(self, target_id: UUID) -> ValidationTarget:
        """Return the target identified by *target_id*.

        Raises:
            NotFoundError: If no such target exists.
        """
        return await self._targets.require_by_id(target_id)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationTarget]:
        """Every validation target belonging to *organization_id*."""
        return await self._targets.list_for_org(organization_id)

    async def list_by_ids(self, target_ids: list[UUID]) -> list[ValidationTarget]:
        """Resolve an execution's own ``target_ids`` into their actual rows."""
        return await self._targets.list_by_ids(target_ids)

    async def get_or_create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        target_type: ValidationTargetType,
        external_id: str,
        name: str,
        target_metadata: dict[str, Any],
    ) -> ValidationTarget:
        """Reuse the target already registered for this external asset, or
        register a new one.
        """
        existing = await self._targets.get_by_external_id(organization_id, target_type, external_id)
        if existing is not None:
            existing.name = name
            existing.target_metadata = target_metadata
            return await self._targets.update(existing)
        return await self._targets.create(
            ValidationTarget(
                organization_id=organization_id,
                project_id=project_id,
                target_type=target_type,
                external_id=external_id,
                name=name,
                target_metadata=target_metadata,
            )
        )


__all__ = ["ValidationTargetService"]
