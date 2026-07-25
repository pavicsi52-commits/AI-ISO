"""Repository for :class:`app.models.asset_label.AssetLabel`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_label import AssetLabel


class AssetLabelRepository(BaseRepository[AssetLabel]):
    """CRUD plus lookup for :class:`AssetLabel`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetLabel, tenant_scope=tenant_scope)

    async def get_by_key(
        self, asset_id: UUID, key: str, *, namespace: str | None = None
    ) -> AssetLabel | None:
        """Return the label identified by *(namespace, key)* on *asset_id*, or ``None``."""
        stmt = self._base_select().where(
            AssetLabel.asset_id == asset_id,
            AssetLabel.namespace == namespace,
            AssetLabel.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetLabel]:
        """Every label assigned to *asset_id*."""
        stmt = self._base_select().where(AssetLabel.asset_id == asset_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetLabelRepository"]
