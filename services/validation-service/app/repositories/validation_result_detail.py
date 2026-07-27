"""Repository for :class:`app.models.validation_result_detail.ValidationResultDetail`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_result_detail import ValidationResultDetail


class ValidationResultDetailRepository(BaseRepository[ValidationResultDetail]):
    """CRUD plus lookup for :class:`ValidationResultDetail`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationResultDetail, tenant_scope=tenant_scope)

    async def list_for_result(self, result_id: UUID) -> list[ValidationResultDetail]:
        """Every raw collected data point backing *result_id*."""
        stmt = self._base_select().where(ValidationResultDetail.result_id == result_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationResultDetailRepository"]
