"""Repositories for the append-only timeline, worklogs, and assignment history."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.timeline import IncidentAssignment, IncidentTimeline, IncidentWorklog


class TimelineRepository(BaseRepository[IncidentTimeline]):
    """The append-only sequence of what happened."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentTimeline, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 1_000
    ) -> list[IncidentTimeline]:
        """One incident's timeline, oldest first -- the order it happened in."""
        stmt = (
            self._base_select()
            .where(IncidentTimeline.organization_id == organization_id)
            .where(IncidentTimeline.incident_id == incident_id)
            .order_by(IncidentTimeline.occurred_at, IncidentTimeline.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class WorklogRepository(BaseRepository[IncidentWorklog]):
    """Effort actually spent, by whom."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentWorklog, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 500
    ) -> list[IncidentWorklog]:
        """One incident's worklog entries, oldest first."""
        stmt = (
            self._base_select()
            .where(IncidentWorklog.organization_id == organization_id)
            .where(IncidentWorklog.incident_id == incident_id)
            .order_by(IncidentWorklog.logged_at, IncidentWorklog.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AssignmentRepository(BaseRepository[IncidentAssignment]):
    """The history of who has held an incident."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentAssignment, tenant_scope=tenant_scope)

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 200
    ) -> list[IncidentAssignment]:
        """One incident's assignment history, oldest first."""
        stmt = (
            self._base_select()
            .where(IncidentAssignment.organization_id == organization_id)
            .where(IncidentAssignment.incident_id == incident_id)
            .order_by(IncidentAssignment.assigned_at, IncidentAssignment.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def current(self, organization_id: UUID, incident_id: UUID) -> IncidentAssignment | None:
        """The still-open assignment for one incident, if any."""
        stmt = (
            self._base_select()
            .where(IncidentAssignment.organization_id == organization_id)
            .where(IncidentAssignment.incident_id == incident_id)
            .where(IncidentAssignment.unassigned_at.is_(None))
            .order_by(IncidentAssignment.assigned_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AssignmentRepository", "TimelineRepository", "WorklogRepository"]
