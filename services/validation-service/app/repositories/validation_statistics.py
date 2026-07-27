"""Repository for :class:`app.models.validation_statistics.ValidationStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_statistics import ValidationStatistics


class ValidationStatisticsRepository(BaseRepository[ValidationStatistics]):
    """CRUD plus lookup for :class:`ValidationStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> ValidationStatistics | None:
        """Return *organization_id*'s cached analytics snapshot, or ``None``."""
        stmt = self._base_select().where(ValidationStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ValidationStatisticsRepository"]
