"""Repository for :class:`app.models.playbook_variable.PlaybookVariable`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_variable import PlaybookVariable


class PlaybookVariableRepository(BaseRepository[PlaybookVariable]):
    """CRUD plus lookup for :class:`PlaybookVariable`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookVariable, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookVariable]:
        """Every variable definition for *playbook_id*."""
        stmt = self._base_select().where(PlaybookVariable.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookVariableRepository"]
