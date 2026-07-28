"""Repository for :class:`app.models.ai_tool.AiTool`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_tool import AiTool


class AiToolRepository(BaseRepository[AiTool]):
    """CRUD plus lookup for :class:`AiTool`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiTool, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiTool]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiTool.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, organization_id: UUID, tool_key: str) -> AiTool | None:
        """Return the tool registered under *tool_key*, if any."""
        stmt = self._base_select().where(
            AiTool.organization_id == organization_id, AiTool.tool_key == tool_key
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AiTool]:
        """Every enabled tool for *organization_id*."""
        stmt = self._base_select().where(
            AiTool.organization_id == organization_id, AiTool.enabled.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiToolRepository"]
