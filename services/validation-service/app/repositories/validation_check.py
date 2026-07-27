"""Repository for :class:`app.models.validation_check.ValidationCheck`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_check import ValidationCheck


class ValidationCheckRepository(BaseRepository[ValidationCheck]):
    """CRUD plus lookup for :class:`ValidationCheck`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationCheck, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ValidationCheck]:
        """Every reusable check defined for *organization_id*."""
        stmt = self._base_select().where(ValidationCheck.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(self, check_ids: list[UUID]) -> list[ValidationCheck]:
        """Resolve a profile's own ``check_ids`` into their actual rows.

        Silently skips any id with no matching row (e.g. a check
        deleted after a profile referenced it) rather than raising --
        a profile is a snapshot-by-reference, not a hard dependency.
        """
        if not check_ids:
            return []
        stmt = self._base_select().where(ValidationCheck.id.in_(check_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationCheckRepository"]
