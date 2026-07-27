"""Repository for :class:`app.models.validation_score.ValidationScore`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_score import ValidationScore


class ValidationScoreRepository(BaseRepository[ValidationScore]):
    """CRUD plus lookup for :class:`ValidationScore`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ValidationScore, tenant_scope=tenant_scope)

    async def get_for_execution(self, execution_id: UUID) -> ValidationScore | None:
        """Return *execution_id*'s own weighted score, or ``None`` if not yet computed."""
        stmt = self._base_select().where(ValidationScore.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ValidationScoreRepository"]
