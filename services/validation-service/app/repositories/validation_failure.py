"""Repository for :class:`app.models.validation_failure.ValidationFailure`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_failure import ValidationFailure


class ValidationFailureRepository(BaseRepository[ValidationFailure]):
    """CRUD plus lookup for :class:`ValidationFailure`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationFailure, tenant_scope=tenant_scope)

    async def list_for_result(self, result_id: UUID) -> list[ValidationFailure]:
        """Every failure recorded for *result_id*."""
        stmt = self._base_select().where(ValidationFailure.result_id == result_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_unresolved_for_org(self, organization_id: UUID) -> list[ValidationFailure]:
        """Every unresolved failure for *organization_id*."""
        stmt = self._base_select().where(
            ValidationFailure.organization_id == organization_id,
            ValidationFailure.is_resolved.is_(False),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationFailureRepository"]
