"""Repository for :class:`app.models.validation_target.ValidationTarget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationTargetType
from app.models.validation_target import ValidationTarget


class ValidationTargetRepository(BaseRepository[ValidationTarget]):
    """CRUD plus lookup for :class:`ValidationTarget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationTarget, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationTarget]:
        """Every validation target belonging to *organization_id*."""
        stmt = self._base_select().where(ValidationTarget.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, target_ids: list[UUID]) -> list[ValidationTarget]:
        """Resolve an execution's own ``target_ids`` into their actual rows."""
        if not target_ids:
            return []
        stmt = self._base_select().where(ValidationTarget.id.in_(target_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_external_id(
        self, organization_id: UUID, target_type: ValidationTargetType, external_id: str
    ) -> ValidationTarget | None:
        """Return the target already registered for this external asset, if any.

        Lets callers re-validate the same inventory asset/automation
        job/etc. across many executions without registering a fresh
        duplicate :class:`ValidationTarget` row every time.
        """
        stmt = self._base_select().where(
            ValidationTarget.organization_id == organization_id,
            ValidationTarget.target_type == target_type,
            ValidationTarget.external_id == external_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ValidationTargetRepository"]
