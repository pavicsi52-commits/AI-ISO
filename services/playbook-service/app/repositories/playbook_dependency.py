"""Repository for :class:`app.models.playbook_dependency.PlaybookDependency`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_dependency import PlaybookDependency


class PlaybookDependencyRepository(BaseRepository[PlaybookDependency]):
    """CRUD plus lookup for :class:`PlaybookDependency`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookDependency, tenant_scope=tenant_scope)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookDependency]:
        """Every dependency declared by *playbook_id*."""
        stmt = self._base_select().where(PlaybookDependency.playbook_id == playbook_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookDependencyRepository"]
