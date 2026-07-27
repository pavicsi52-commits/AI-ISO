"""Repository for :class:`app.models.playbook_repository.PlaybookRepositoryFolder`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_repository import PlaybookRepositoryFolder


class PlaybookRepositoryFolderRepository(BaseRepository[PlaybookRepositoryFolder]):
    """CRUD plus lookup for :class:`PlaybookRepositoryFolder`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookRepositoryFolder, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[PlaybookRepositoryFolder]:
        """Every repository folder belonging to *organization_id*."""
        stmt = self._base_select().where(
            PlaybookRepositoryFolder.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookRepositoryFolderRepository"]
