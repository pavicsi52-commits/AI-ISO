"""Repository for :class:`app.models.permission.AgentPermissionGrant`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionCategory, PermissionGrantStatus
from app.models.permission import AgentPermissionGrant


class AgentPermissionGrantRepository(BaseRepository[AgentPermissionGrant]):
    """CRUD plus lookup for :class:`AgentPermissionGrant`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentPermissionGrant, tenant_scope=tenant_scope)

    async def get_for_category(
        self, agent_id: UUID, category: PermissionCategory
    ) -> AgentPermissionGrant | None:
        """Return *agent_id*'s own grant for *category*, or ``None``."""
        stmt = self._base_select().where(
            AgentPermissionGrant.agent_id == agent_id, AgentPermissionGrant.category == category
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_granted(self, agent_id: UUID) -> list[AgentPermissionGrant]:
        """Every currently-``GRANTED`` category for *agent_id* -- the
        exact set :mod:`app.tool_registry.registry`'s own ``authorize()``
        checks a tool call's own ``required_permission`` against.
        """
        stmt = self._base_select().where(
            AgentPermissionGrant.agent_id == agent_id,
            AgentPermissionGrant.status == PermissionGrantStatus.GRANTED,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_agent(self, agent_id: UUID) -> list[AgentPermissionGrant]:
        """Every permission row for *agent_id*, granted or not."""
        stmt = self._base_select().where(AgentPermissionGrant.agent_id == agent_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentPermissionGrantRepository"]
