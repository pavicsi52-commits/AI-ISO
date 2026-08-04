"""The incident repository.

Every read is scoped by ``organization_id``, including the lookup by
reference -- ``INC-0042`` is a human-quotable identifier printed on
status pages and said out loud on bridge calls, so an unscoped lookup by
reference would let one tenant read another's incident by guessing a
small, sequential number. ``require_in_org`` is named apart from the
base repository's unscoped ``require_by_id`` for the same reason
Prompt 050 and 051 established it: two same-named methods of different
arity on one class make an unscoped call look correct.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    OPEN_INCIDENT_STATUSES,
    IncidentCategory,
    IncidentPriority,
    IncidentStatus,
)
from app.models.incident import Incident


class IncidentRepository(BaseRepository[Incident]):
    """The incident catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Incident, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, incident_id: UUID) -> Incident:
        """One incident by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. Deliberately not a
                permission error -- telling a caller it exists but
                belongs to someone else confirms the id, which is the
                one thing they did not already know.
        """
        stmt = (
            self._base_select()
            .where(Incident.organization_id == organization_id)
            .where(Incident.id == incident_id)
        )
        result = await self._session.execute(stmt)
        found: Incident | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No incident with id {incident_id} in this organization.")
        return found

    async def get_by_reference(self, organization_id: UUID, reference: str) -> Incident | None:
        """One incident by its human-quotable reference."""
        stmt = (
            self._base_select()
            .where(Incident.organization_id == organization_id)
            .where(Incident.reference == reference)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_open_by_fingerprint(
        self, organization_id: UUID, fingerprint: str
    ) -> list[Incident]:
        """Open incidents sharing a fingerprint, newest first.

        Every open match, not just one -- correlation
        (``app/incidents/engine.py::correlates``) still has to check the
        activity window against each candidate, and returning only the
        first would let a stale open incident shadow a genuinely newer
        one with the same fingerprint.
        """
        stmt = (
            self._base_select()
            .where(Incident.organization_id == organization_id)
            .where(Incident.fingerprint == fingerprint)
            .where(Incident.status.in_([str(one) for one in OPEN_INCIDENT_STATUSES]))
            .order_by(Incident.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def next_reference_sequence(self, organization_id: UUID) -> int:
        """The next number to use in this organization's ``INC-####`` series.

        Derived from the highest existing reference rather than a
        row count, so a deleted incident does not cause the next
        reference to be reused -- a reference already quoted on a status
        page or in a postmortem must stay unique forever.
        """
        stmt = select(Incident.reference).where(Incident.organization_id == organization_id)
        result = await self._session.execute(stmt)
        highest = 0
        for (reference,) in result.all():
            _, _, tail = reference.rpartition("-")
            if tail.isdigit():
                highest = max(highest, int(tail))
        return highest + 1

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: IncidentStatus | None = None,
        priority: IncidentPriority | None = None,
        category: IncidentCategory | None = None,
        assignee_id: str | None = None,
        is_major: bool | None = None,
        open_only: bool = False,
        problem_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Incident]:
        """Incidents matching a caller's filters, newest first."""
        stmt = self._base_select().where(Incident.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(Incident.status == str(status))
        if priority is not None:
            stmt = stmt.where(Incident.priority == str(priority))
        if category is not None:
            stmt = stmt.where(Incident.category == str(category))
        if assignee_id is not None:
            stmt = stmt.where(Incident.assignee_id == assignee_id)
        if is_major is not None:
            stmt = stmt.where(Incident.is_major.is_(is_major))
        if problem_id is not None:
            stmt = stmt.where(Incident.problem_id == problem_id)
        if open_only:
            stmt = stmt.where(Incident.status.in_([str(one) for one in OPEN_INCIDENT_STATUSES]))
        stmt = stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open(self, organization_id: UUID, *, limit: int = 500) -> list[Incident]:
        """Every open incident, for load-balancing and dashboards."""
        return await self.list_filtered(organization_id, open_only=True, limit=limit)

    async def count_open_for_assignee(self, organization_id: UUID, assignee_id: str) -> int:
        """How many open incidents one responder currently carries.

        What the assignment engine's load-balancing reads -- see
        ``app/assignment/engine.py``.
        """
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(Incident.organization_id == organization_id)
            .where(Incident.assignee_id == assignee_id)
            .where(Incident.status.in_([str(one) for one in OPEN_INCIDENT_STATUSES]))
            .where(Incident.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[Incident]:
        """Incidents created within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(Incident.organization_id == organization_id)
            .where(Incident.created_at >= start)
            .where(Incident.created_at < end)
            .order_by(Incident.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many incidents sit in each lifecycle status."""
        stmt = (
            select(Incident.status, func.count())
            .where(Incident.organization_id == organization_id)
            .where(Incident.deleted_at.is_(None))
            .group_by(Incident.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_merged_into(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 200
    ) -> list[Incident]:
        """Every incident merged into this one."""
        stmt = (
            self._base_select()
            .where(Incident.organization_id == organization_id)
            .where(Incident.merged_into_id == incident_id)
            .order_by(Incident.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["IncidentRepository"]
