"""Repository for :class:`app.models.playbook_script.PlaybookScript`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_script import PlaybookScript


class PlaybookScriptRepository(BaseRepository[PlaybookScript]):
    """CRUD plus lookup for :class:`PlaybookScript`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookScript, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookScript]:
        """Every auxiliary script file bundled with *playbook_id*."""
        stmt = self._base_select().where(PlaybookScript.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookScriptRepository"]
