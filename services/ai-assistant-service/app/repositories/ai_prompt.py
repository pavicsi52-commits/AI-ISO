"""Repository for :class:`app.models.ai_prompt.AiPrompt`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_prompt import AiPrompt


class AiPromptRepository(BaseRepository[AiPrompt]):
    """CRUD plus lookup for :class:`AiPrompt`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiPrompt, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiPrompt]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiPrompt.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiPromptRepository"]
