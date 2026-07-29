"""Repository for :class:`app.models.graph_metadata.GraphMetadata`."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LifecycleState, TwinType
from app.models.graph_metadata import GraphMetadata


class GraphMetadataRepository(BaseRepository[GraphMetadata]):
    """CRUD plus lookups for :class:`GraphMetadata`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphMetadata, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        twin_type: TwinType | None = None,
        lifecycle_state: LifecycleState | None = None,
        limit: int = 500,
    ) -> list[GraphMetadata]:
        """Metadata rows for one organization."""
        stmt = self._base_select().where(GraphMetadata.organization_id == organization_id)
        if twin_type is not None:
            stmt = stmt.where(GraphMetadata.twin_type == twin_type)
        if lifecycle_state is not None:
            stmt = stmt.where(GraphMetadata.lifecycle_state == lifecycle_state)
        stmt = stmt.order_by(GraphMetadata.node_key).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_node(self, organization_id: UUID, node_key: str) -> GraphMetadata | None:
        """Metadata for one node, if it has any."""
        stmt = self._base_select().where(
            GraphMetadata.organization_id == organization_id,
            GraphMetadata.node_key == node_key,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_many(
        self, organization_id: UUID, node_keys: Sequence[str]
    ) -> dict[str, GraphMetadata]:
        """Metadata for many nodes at once, keyed by node key.

        One query rather than one per node: enriching a 500-node
        traversal result would otherwise be 500 round trips.
        """
        if not node_keys:
            return {}
        stmt = self._base_select().where(
            GraphMetadata.organization_id == organization_id,
            GraphMetadata.node_key.in_(list(node_keys)),
        )
        result = await self._session.execute(stmt)
        return {row.node_key: row for row in result.scalars().all()}

    async def list_pinned(self, organization_id: UUID) -> list[GraphMetadata]:
        """Nodes excluded from synchronization deletes."""
        stmt = self._base_select().where(
            GraphMetadata.organization_id == organization_id,
            GraphMetadata.is_pinned.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_critical(
        self, organization_id: UUID, *, threshold: float = 0.7, limit: int = 50
    ) -> list[GraphMetadata]:
        """The nodes an operator has declared most important."""
        stmt = (
            self._base_select()
            .where(
                GraphMetadata.organization_id == organization_id,
                GraphMetadata.criticality >= threshold,
            )
            .order_by(desc(GraphMetadata.criticality))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphMetadataRepository"]
