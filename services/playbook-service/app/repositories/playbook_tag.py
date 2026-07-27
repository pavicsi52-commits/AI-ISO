"""Repository for :class:`app.models.playbook_tag.PlaybookTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_tag import PlaybookTag


class PlaybookTagRepository(BaseRepository[PlaybookTag]):
    """CRUD plus lookup for :class:`PlaybookTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookTag, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookTag]:
        """Every tag assigned to *playbook_id*."""
        stmt = self._base_select().where(PlaybookTag.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_tag(self, playbook_id: UUID, tag: str) -> PlaybookTag | None:
        """Return *playbook_id*'s own *tag* row, or ``None``."""
        stmt = self._base_select().where(
            PlaybookTag.playbook_id == playbook_id, PlaybookTag.tag == tag
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["PlaybookTagRepository"]
