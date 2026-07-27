"""Repository for :class:`app.models.playbook_label.PlaybookLabel`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_label import PlaybookLabel


class PlaybookLabelRepository(BaseRepository[PlaybookLabel]):
    """CRUD plus lookup for :class:`PlaybookLabel`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookLabel, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookLabel]:
        """Every label assigned to *playbook_id*."""
        stmt = self._base_select().where(PlaybookLabel.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, playbook_id: UUID, key: str) -> PlaybookLabel | None:
        """Return *playbook_id*'s own label named *key*, or ``None``."""
        stmt = self._base_select().where(
            PlaybookLabel.playbook_id == playbook_id, PlaybookLabel.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["PlaybookLabelRepository"]
