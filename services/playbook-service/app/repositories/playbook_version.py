"""Repository for :class:`app.models.playbook_version.PlaybookVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_version import PlaybookVersion


class PlaybookVersionRepository(BaseRepository[PlaybookVersion]):
    """CRUD plus lookup for :class:`PlaybookVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookVersion, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookVersion]:
        """Every version recorded for *playbook_id*, newest first."""
        stmt = (
            self._base_select()
            .where(PlaybookVersion.playbook_id == playbook_id)
            .order_by(desc(PlaybookVersion.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_playbook(self, playbook_id: UUID) -> PlaybookVersion | None:
        """Return *playbook_id*'s most recently created version, or ``None``."""
        stmt = (
            self._base_select()
            .where(PlaybookVersion.playbook_id == playbook_id)
            .order_by(desc(PlaybookVersion.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["PlaybookVersionRepository"]
