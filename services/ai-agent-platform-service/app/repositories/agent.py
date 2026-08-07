"""Repositories for :class:`app.models.agent.Agent` and
:class:`app.models.agent.AgentVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentVersion
from app.models.enums import AgentType


class AgentRepository(BaseRepository[Agent]):
    """CRUD plus lookup for :class:`Agent`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Agent, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, agent_id: UUID) -> Agent:
        """Return *agent_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such agent exists in that organization.
        """
        stmt = self._base_select().where(
            Agent.id == agent_id, Agent.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        agent = result.scalars().first()
        if agent is None:
            raise NotFoundError(
                f"Agent {agent_id!s} was not found in organization {organization_id!s}."
            )
        return agent

    async def get_by_slug(self, organization_id: UUID, slug: str) -> Agent | None:
        """Return the agent with *slug* in *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            Agent.organization_id == organization_id, Agent.slug == slug
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_type(self, organization_id: UUID, agent_type: AgentType) -> list[Agent]:
        """Every agent of *agent_type* in *organization_id*."""
        stmt = self._base_select().where(
            Agent.organization_id == organization_id, Agent.agent_type == agent_type
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[Agent]:
        """Every agent registered in *organization_id*."""
        stmt = self._base_select().where(Agent.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AgentVersionRepository(BaseRepository[AgentVersion]):
    """CRUD plus lookup for :class:`AgentVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentVersion, tenant_scope=tenant_scope)

    async def list_for_agent(self, agent_id: UUID) -> list[AgentVersion]:
        """Every version snapshot for *agent_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.released_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current(self, agent_id: UUID) -> AgentVersion | None:
        """Return *agent_id*'s own currently-activated version, if any."""
        stmt = self._base_select().where(
            AgentVersion.agent_id == agent_id, AgentVersion.is_current.is_(True)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AgentRepository", "AgentVersionRepository"]
