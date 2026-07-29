"""Repository for :class:`app.models.graph_version.GraphVersion`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_version import GraphVersion


class GraphVersionRepository(BaseRepository[GraphVersion]):
    """CRUD plus lookups for :class:`GraphVersion`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphVersion, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID, *, limit: int = 100) -> list[GraphVersion]:
        """Versions for one organization, newest first."""
        stmt = (
            self._base_select()
            .where(GraphVersion.organization_id == organization_id)
            .order_by(desc(GraphVersion.sequence))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sequence(self, organization_id: UUID, sequence: int) -> GraphVersion | None:
        """One version by its per-organization sequence number."""
        stmt = self._base_select().where(
            GraphVersion.organization_id == organization_id,
            GraphVersion.sequence == sequence,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def next_sequence(self, organization_id: UUID) -> int:
        """The next sequence number, computed in SQL.

        ``MAX + 1`` in the database rather than ``len(rows) + 1`` in
        Python: the latter reuses a number as soon as any version is
        deleted, and the unique constraint would then reject the write.
        """
        stmt = (
            self._base_select()
            .with_only_columns(func.max(GraphVersion.sequence))
            .where(GraphVersion.organization_id == organization_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one_or_none() or 0) + 1


__all__ = ["GraphVersionRepository"]
