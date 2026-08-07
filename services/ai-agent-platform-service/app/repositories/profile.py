"""Repository for :class:`app.models.profile.AgentProfile`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgentProfile


class AgentProfileRepository(BaseRepository[AgentProfile]):
    """CRUD plus lookup for :class:`AgentProfile`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentProfile, tenant_scope=tenant_scope)

    async def get_for_agent(self, agent_id: UUID) -> AgentProfile | None:
        """Return *agent_id*'s own configuration profile, or ``None``."""
        stmt = self._base_select().where(AgentProfile.agent_id == agent_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def require_for_agent(self, agent_id: UUID) -> AgentProfile:
        """Return *agent_id*'s own configuration profile.

        Raises:
            NotFoundError: If *agent_id* has no profile yet.
        """
        profile = await self.get_for_agent(agent_id)
        if profile is None:
            raise NotFoundError(f"Agent {agent_id!s} has no configuration profile.")
        return profile


__all__ = ["AgentProfileRepository"]
