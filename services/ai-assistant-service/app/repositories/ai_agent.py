"""Repository for :class:`app.models.ai_agent.AiAgent`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_agent import AiAgent


class AiAgentRepository(BaseRepository[AiAgent]):
    """CRUD plus lookup for :class:`AiAgent`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiAgent, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiAgent]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiAgent.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, organization_id: UUID, name: str) -> AiAgent | None:
        """Return the agent registered under *name*, if any."""
        stmt = self._base_select().where(
            AiAgent.organization_id == organization_id, AiAgent.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AiAgent]:
        """Every enabled agent for *organization_id*."""
        stmt = self._base_select().where(
            AiAgent.organization_id == organization_id, AiAgent.enabled.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiAgentRepository"]
