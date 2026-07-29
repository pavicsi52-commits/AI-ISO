"""Repository for :class:`app.models.graph_snapshot.GraphSnapshot`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.graph_snapshot import GraphSnapshot


class GraphSnapshotRepository(BaseRepository[GraphSnapshot]):
    """CRUD plus lookups for :class:`GraphSnapshot`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphSnapshot, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID, *, limit: int = 100) -> list[GraphSnapshot]:
        """Snapshots for one organization, newest first.

        Deliberately selects every column *except* the payload would be
        the obvious optimisation, but SQLAlchemy would then emit a
        second query per row on first access. Callers that only need
        the listing use :meth:`list_summaries` instead.
        """
        stmt = (
            self._base_select()
            .where(GraphSnapshot.organization_id == organization_id)
            .order_by(desc(GraphSnapshot.captured_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_summaries(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[tuple[UUID, str, JobStatus, int, int, datetime]]:
        """Snapshot listings without their payloads.

        A snapshot payload is the whole graph; loading fifty of them to
        render a list would move hundreds of megabytes to answer a
        question about labels and timestamps.
        """
        stmt = (
            self._base_select()
            .with_only_columns(
                GraphSnapshot.id,
                GraphSnapshot.label,
                GraphSnapshot.status,
                GraphSnapshot.node_count,
                GraphSnapshot.relationship_count,
                GraphSnapshot.captured_at,
            )
            .where(GraphSnapshot.organization_id == organization_id)
            .order_by(desc(GraphSnapshot.captured_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [tuple(row) for row in result.all()]  # type: ignore[misc]

    async def list_expired(self, organization_id: UUID, *, moment: datetime) -> list[GraphSnapshot]:
        """Snapshots past their expiry, for the retention sweep."""
        stmt = self._base_select().where(
            GraphSnapshot.organization_id == organization_id,
            GraphSnapshot.expires_at.is_not(None),
            GraphSnapshot.expires_at <= moment,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphSnapshotRepository"]
