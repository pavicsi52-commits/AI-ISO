"""Repository for :class:`app.models.playbook_category.PlaybookCategory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook_category import PlaybookCategory


class PlaybookCategoryRepository(BaseRepository[PlaybookCategory]):
    """CRUD plus lookup for :class:`PlaybookCategory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookCategory, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[PlaybookCategory]:
        """Every category belonging to *organization_id*."""
        stmt = self._base_select().where(PlaybookCategory.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookCategoryRepository"]
