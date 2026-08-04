"""Repositories for root causes, problem records, and known errors."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProblemStatus
from app.models.rca import IncidentRootCause, KnownError, ProblemRecord


class RootCauseRepository(BaseRepository[IncidentRootCause]):
    """Root cause findings."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, IncidentRootCause, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, root_cause_id: UUID) -> IncidentRootCause:
        """One finding by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(IncidentRootCause.organization_id == organization_id)
            .where(IncidentRootCause.id == root_cause_id)
        )
        result = await self._session.execute(stmt)
        found: IncidentRootCause | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No root cause finding with id {root_cause_id} in this organization."
            )
        return found

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID, *, limit: int = 100
    ) -> list[IncidentRootCause]:
        """Every finding for one incident, oldest first -- how understanding evolved."""
        stmt = (
            self._base_select()
            .where(IncidentRootCause.organization_id == organization_id)
            .where(IncidentRootCause.incident_id == incident_id)
            .order_by(IncidentRootCause.recorded_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_confirmed(
        self, organization_id: UUID, incident_id: UUID
    ) -> IncidentRootCause | None:
        """The most recent confirmed finding, if any -- what a postmortem cites."""
        stmt = (
            self._base_select()
            .where(IncidentRootCause.organization_id == organization_id)
            .where(IncidentRootCause.incident_id == incident_id)
            .where(IncidentRootCause.is_confirmed.is_(True))
            .order_by(IncidentRootCause.recorded_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ProblemRepository(BaseRepository[ProblemRecord]):
    """Recurring-pattern records."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProblemRecord, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, problem_id: UUID) -> ProblemRecord:
        """One problem by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ProblemRecord.organization_id == organization_id)
            .where(ProblemRecord.id == problem_id)
        )
        result = await self._session.execute(stmt)
        found: ProblemRecord | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No problem with id {problem_id} in this organization.")
        return found

    async def existing_references(self, organization_id: UUID) -> list[str]:
        """Every reference already issued, for computing the next one."""
        stmt = select(ProblemRecord.reference).where(
            ProblemRecord.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ProblemStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ProblemRecord]:
        """Problems matching a caller's filters, newest first."""
        stmt = self._base_select().where(ProblemRecord.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ProblemRecord.status == str(status))
        stmt = stmt.order_by(ProblemRecord.identified_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class KnownErrorRepository(BaseRepository[KnownError]):
    """Known errors -- understood problems with no permanent fix yet."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, KnownError, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, known_error_id: UUID) -> KnownError:
        """One known error by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(KnownError.organization_id == organization_id)
            .where(KnownError.id == known_error_id)
        )
        result = await self._session.execute(stmt)
        found: KnownError | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No known error with id {known_error_id} in this organization.")
        return found

    async def list_for_problem(self, organization_id: UUID, problem_id: UUID) -> list[KnownError]:
        """Every known error tied to one problem."""
        stmt = (
            self._base_select()
            .where(KnownError.organization_id == organization_id)
            .where(KnownError.problem_id == problem_id)
            .order_by(KnownError.recorded_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[KnownError]:
        """Every active known error -- the 03:00 triage lookup."""
        stmt = (
            self._base_select()
            .where(KnownError.organization_id == organization_id)
            .where(KnownError.is_active.is_(True))
            .order_by(KnownError.recorded_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["KnownErrorRepository", "ProblemRepository", "RootCauseRepository"]
