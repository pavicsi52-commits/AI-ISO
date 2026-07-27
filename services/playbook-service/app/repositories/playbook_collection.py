"""Repository for :class:`app.models.playbook_collection.PlaybookCollection`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_collection import PlaybookCollection


class PlaybookCollectionRepository(BaseRepository[PlaybookCollection]):
    """CRUD plus lookup for :class:`PlaybookCollection`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookCollection, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookCollection]:
        """Every Ansible collection *playbook_id* references."""
        stmt = self._base_select().where(PlaybookCollection.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookCollectionRepository"]
