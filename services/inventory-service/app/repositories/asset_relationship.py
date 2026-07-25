"""Repository for :class:`app.models.asset_relationship.AssetRelationship`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_relationship import AssetRelationship
from app.models.enums import RelationshipType


class AssetRelationshipRepository(BaseRepository[AssetRelationship]):
    """CRUD plus lookup for :class:`AssetRelationship`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetRelationship, tenant_scope=tenant_scope)

    async def get_by_edge(
        self, source_asset_id: UUID, target_asset_id: UUID, relationship_type: RelationshipType
    ) -> AssetRelationship | None:
        """Return the edge identified by *(source, target, type)*, or ``None``."""
        stmt = self._base_select().where(
            AssetRelationship.source_asset_id == source_asset_id,
            AssetRelationship.target_asset_id == target_asset_id,
            AssetRelationship.relationship_type == relationship_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[AssetRelationship]:
        """Every relationship touching *asset_id*, as either source or target."""
        stmt = self._base_select().where(
            or_(
                AssetRelationship.source_asset_id == asset_id,
                AssetRelationship.target_asset_id == asset_id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetRelationshipRepository"]
