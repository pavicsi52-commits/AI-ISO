"""Repository for :class:`app.models.validation_result.ValidationResult`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_result import ValidationResult


class ValidationResultRepository(BaseRepository[ValidationResult]):
    """CRUD plus lookup for :class:`ValidationResult`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationResult, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[ValidationResult]:
        """Every result recorded for *execution_id*."""
        stmt = self._base_select().where(ValidationResult.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_target(self, target_id: UUID) -> list[ValidationResult]:
        """Every result ever recorded for *target_id*, across every execution."""
        stmt = self._base_select().where(ValidationResult.target_id == target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationResultRepository"]
