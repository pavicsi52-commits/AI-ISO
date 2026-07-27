"""Repository for :class:`app.models.validation_history.ValidationHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_history import ValidationHistory


class ValidationHistoryRepository(BaseRepository[ValidationHistory]):
    """CRUD plus lookup for :class:`ValidationHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationHistory, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[ValidationHistory]:
        """Every historical snapshot for *target_id*, oldest first ("Asset Health Trends")."""
        stmt = (
            self._base_select()
            .where(ValidationHistory.target_id == target_id)
            .order_by(ValidationHistory.recorded_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[ValidationHistory]:
        """Every historical snapshot for *organization_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(ValidationHistory.organization_id == organization_id)
            .order_by(ValidationHistory.recorded_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ValidationHistoryRepository"]
