"""Repository for :class:`app.models.ai_feedback.AiFeedback`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_feedback import AiFeedback


class AiFeedbackRepository(BaseRepository[AiFeedback]):
    """CRUD plus lookup for :class:`AiFeedback`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiFeedback, tenant_scope=tenant_scope)

    async def list_for_message(self, message_id: UUID) -> list[AiFeedback]:
        """Every rating submitted for one message."""
        stmt = self._base_select().where(AiFeedback.message_id == message_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[AiFeedback]:
        """Every rating for *organization_id* (analytics rollups)."""
        stmt = self._base_select().where(AiFeedback.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiFeedbackRepository"]
