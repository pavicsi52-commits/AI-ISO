"""Repository for :class:`app.models.ai_prompt_version.AiPromptVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_prompt_version import AiPromptVersion


class AiPromptVersionRepository(BaseRepository[AiPromptVersion]):
    """CRUD plus lookup for :class:`AiPromptVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiPromptVersion, tenant_scope=tenant_scope)

    async def list_for_prompt(self, prompt_id: UUID) -> list[AiPromptVersion]:
        """Every revision of a prompt."""
        stmt = self._base_select().where(AiPromptVersion.prompt_id == prompt_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_version(self, prompt_id: UUID, version_number: str) -> AiPromptVersion | None:
        """Return one specific revision, if it exists."""
        stmt = self._base_select().where(
            AiPromptVersion.prompt_id == prompt_id,
            AiPromptVersion.version_number == version_number,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AiPromptVersionRepository"]
