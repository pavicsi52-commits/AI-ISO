"""Repository for :class:`app.models.asset_dependency_analysis.AssetDependencyAnalysis`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_dependency_analysis import AssetDependencyAnalysis


class AssetDependencyAnalysisRepository(BaseRepository[AssetDependencyAnalysis]):
    """CRUD plus lookup for :class:`AssetDependencyAnalysis`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetDependencyAnalysis, tenant_scope=tenant_scope)

    async def get_for_managed_asset(self, managed_asset_id: UUID) -> AssetDependencyAnalysis | None:
        """Return *managed_asset_id*'s cached dependency analysis, or ``None``."""
        stmt = self._base_select().where(
            AssetDependencyAnalysis.managed_asset_id == managed_asset_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AssetDependencyAnalysisRepository"]
