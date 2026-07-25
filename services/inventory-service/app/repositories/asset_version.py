"""Repository for :class:`app.models.asset_version.AssetVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_version import AssetVersion


class AssetVersionRepository(BaseRepository[AssetVersion]):
    """CRUD plus lookup for :class:`AssetVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetVersion, tenant_scope=tenant_scope)

    async def get_latest(self, asset_id: UUID) -> AssetVersion | None:
        """Return *asset_id*'s most recent snapshot, or ``None``."""
        stmt = (
            self._base_select()
            .where(AssetVersion.asset_id == asset_id)
            .order_by(desc(AssetVersion.version_number))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_number(self, asset_id: UUID, version_number: int) -> AssetVersion | None:
        """Return *asset_id*'s version identified by *version_number*, or ``None``."""
        stmt = self._base_select().where(
            AssetVersion.asset_id == asset_id, AssetVersion.version_number == version_number
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetVersion]:
        """Every version of *asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetVersion.asset_id == asset_id)
            .order_by(desc(AssetVersion.version_number))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetVersionRepository"]
