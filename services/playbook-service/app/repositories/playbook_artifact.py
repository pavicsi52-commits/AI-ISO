"""Repository for :class:`app.models.playbook_artifact.PlaybookArtifact`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_artifact import PlaybookArtifact


class PlaybookArtifactRepository(BaseRepository[PlaybookArtifact]):
    """CRUD plus lookup for :class:`PlaybookArtifact`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookArtifact, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookArtifact]:
        """Every artifact recorded for *playbook_id*."""
        stmt = self._base_select().where(PlaybookArtifact.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_version(self, version_id: UUID) -> list[PlaybookArtifact]:
        """Every artifact recorded for *version_id*."""
        stmt = self._base_select().where(PlaybookArtifact.version_id == version_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookArtifactRepository"]
