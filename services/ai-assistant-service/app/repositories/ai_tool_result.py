"""Repository for :class:`app.models.ai_tool_result.AiToolResult`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_tool_result import AiToolResult


class AiToolResultRepository(BaseRepository[AiToolResult]):
    """CRUD plus lookup for :class:`AiToolResult`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiToolResult, tenant_scope=tenant_scope)

    async def get_for_call(self, tool_call_id: UUID) -> AiToolResult | None:
        """Return what one tool call returned, if it completed."""
        stmt = self._base_select().where(AiToolResult.tool_call_id == tool_call_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AiToolResultRepository"]
