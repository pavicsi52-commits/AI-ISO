"""Repository for :class:`app.models.ai_tool_call.AiToolCall`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_tool_call import AiToolCall


class AiToolCallRepository(BaseRepository[AiToolCall]):
    """CRUD plus lookup for :class:`AiToolCall`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiToolCall, tenant_scope=tenant_scope)

    async def list_for_conversation(self, conversation_id: UUID) -> list[AiToolCall]:
        """Every tool call made within one conversation."""
        stmt = self._base_select().where(AiToolCall.conversation_id == conversation_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[AiToolCall]:
        """Every tool call for *organization_id* (analytics rollups)."""
        stmt = self._base_select().where(AiToolCall.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiToolCallRepository"]
