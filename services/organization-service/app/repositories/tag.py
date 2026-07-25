"""Repository for :class:`app.models.tag.OrganizationTag`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import OrganizationTag


class OrganizationTagRepository(BaseRepository[OrganizationTag]):
    """CRUD plus lookup for :class:`OrganizationTag`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationTag, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[OrganizationTag]:
        """Every tag assigned to *organization_id*."""
        stmt = self._base_select().where(OrganizationTag.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_label(self, organization_id: UUID, label: str) -> OrganizationTag | None:
        """Return *organization_id*'s tag matching *label*, or ``None``."""
        stmt = self._base_select().where(
            OrganizationTag.organization_id == organization_id, OrganizationTag.label == label
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationTagRepository"]
