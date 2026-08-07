"""Repository for :class:`app.models.tool.AgentTool`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import AgentTool


class AgentToolRepository(BaseRepository[AgentTool]):
    """CRUD plus lookup for :class:`AgentTool`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentTool, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, tool_id: UUID) -> AgentTool:
        """Return *tool_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such tool exists in that organization.
        """
        stmt = self._base_select().where(
            AgentTool.id == tool_id, AgentTool.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentTool {tool_id!s} was not found in organization {organization_id!s}."
            )
        return found

    async def get_by_key(self, organization_id: UUID, tool_key: str) -> AgentTool | None:
        """Return the tool named *tool_key* in *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            AgentTool.organization_id == organization_id, AgentTool.tool_key == tool_key
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_enabled(self, organization_id: UUID) -> list[AgentTool]:
        """Every enabled, non-deprecated tool in *organization_id*."""
        stmt = self._base_select().where(
            AgentTool.organization_id == organization_id,
            AgentTool.enabled.is_(True),
            AgentTool.is_deprecated.is_(False),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentToolRepository"]
