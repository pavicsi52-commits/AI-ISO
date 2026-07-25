"""Repository for :class:`app.models.activity.OrganizationActivityEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import OrganizationActivityEntry


class OrganizationActivityRepository(BaseRepository[OrganizationActivityEntry]):
    """CRUD plus listing for :class:`OrganizationActivityEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationActivityEntry, tenant_scope=tenant_scope)

    async def list_recent_for_org(
        self, organization_id: UUID, *, limit: int = 50
    ) -> list[OrganizationActivityEntry]:
        """The *limit* most recent activity entries for *organization_id*, newest first."""
        stmt = (
            self._base_select()
            .where(OrganizationActivityEntry.organization_id == organization_id)
            .order_by(desc(OrganizationActivityEntry.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["OrganizationActivityRepository"]
