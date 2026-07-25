"""Repository for :class:`app.models.discovery_relationship.DiscoveryRelationship`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_relationship import DiscoveryRelationship
from app.models.enums import DiscoveryRelationshipType


class DiscoveryRelationshipRepository(BaseRepository[DiscoveryRelationship]):
    """CRUD plus lookup for :class:`DiscoveryRelationship`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryRelationship, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryRelationship]:
        """Every relationship edge detected by *job_id*."""
        stmt = self._base_select().where(DiscoveryRelationship.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_edge(
        self,
        source_discovery_asset_id: UUID,
        target_discovery_asset_id: UUID,
        relationship_type: DiscoveryRelationshipType,
    ) -> DiscoveryRelationship | None:
        """Return the edge identified by *(source, target, type)*, or ``None``."""
        stmt = self._base_select().where(
            DiscoveryRelationship.source_discovery_asset_id == source_discovery_asset_id,
            DiscoveryRelationship.target_discovery_asset_id == target_discovery_asset_id,
            DiscoveryRelationship.relationship_type == relationship_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["DiscoveryRelationshipRepository"]
