"""Repository for :class:`app.models.report_favorite.ReportFavorite`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_favorite import ReportFavorite


class ReportFavoriteRepository(BaseRepository[ReportFavorite]):
    """CRUD plus lookups for :class:`ReportFavorite`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportFavorite, tenant_scope=tenant_scope)

    async def list_for_user(self, organization_id: UUID, user_id: UUID) -> list[ReportFavorite]:
        """Every report one user has pinned."""
        stmt = self._base_select().where(
            ReportFavorite.organization_id == organization_id,
            ReportFavorite.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user_job(self, user_id: UUID, job_id: UUID) -> ReportFavorite | None:
        """One user's favourite of one report, if it exists."""
        stmt = self._base_select().where(
            ReportFavorite.user_id == user_id, ReportFavorite.job_id == job_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ReportFavoriteRepository"]
