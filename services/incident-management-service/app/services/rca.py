"""Root cause findings, recurring-pattern problems, and known errors.

Three closely related concerns: why one incident happened, whether it
is part of a pattern across several incidents, and -- once the pattern
is understood -- what to tell the next person who hits it before a
permanent fix exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.events.incident_events import SOURCE_SERVICE, ProblemCreatedEvent
from app.models.enums import ProblemStatus, RcaMethod
from app.models.rca import IncidentRootCause, KnownError, ProblemRecord
from app.repositories.incident import IncidentRepository
from app.repositories.rca import KnownErrorRepository, ProblemRepository, RootCauseRepository
from app.types import EventPublisher

logger = get_logger("app.services.rca")

_NEXT_REFERENCE_PREFIX = "PRB"


def _next_reference(existing: list[str]) -> str:
    """The next human-quotable problem reference in sequence.

    Derived from the highest existing number rather than a count, so a
    deleted problem does not cause the next reference to be reused --
    the same reasoning as ``IncidentRepository.next_reference_sequence``,
    duplicated here rather than shared because the two series
    (``INC-####`` and ``PRB-####``) are independent and must not collide
    on a shared counter.
    """
    highest = 0
    for one in existing:
        _, _, tail = one.rpartition("-")
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{_NEXT_REFERENCE_PREFIX}-{highest + 1:04d}"


class RootCauseService:
    """Root cause findings on individual incidents."""

    def __init__(self, root_causes: RootCauseRepository, incidents: IncidentRepository) -> None:
        self._root_causes = root_causes
        self._incidents = incidents

    async def record(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        method: RcaMethod,
        summary: str,
        contributing_factors: list[str] | None = None,
        confidence: float = 1.0,
        is_confirmed: bool = False,
        evidence: dict[str, Any] | None = None,
        recorded_by: str | None = None,
        now: datetime | None = None,
    ) -> IncidentRootCause:
        """Record a root cause finding.

        Every finding is kept, not just the latest -- understanding
        evolves during an investigation, and the sequence of findings is
        itself part of what a postmortem's "why did this take so long to
        diagnose" section reads.
        """
        moment = now or datetime.now(UTC)
        stored = await self._incidents.require_in_org(organization_id, incident_id)
        created = await self._root_causes.create(
            IncidentRootCause(
                organization_id=organization_id,
                incident_id=incident_id,
                method=method,
                summary=summary,
                contributing_factors=list(contributing_factors or []),
                confidence=confidence,
                is_confirmed=is_confirmed,
                confirmed_by=recorded_by if is_confirmed else None,
                evidence=dict(evidence or {}),
                recorded_by=recorded_by,
                recorded_at=moment,
                created_by=None,
            )
        )
        if is_confirmed:
            stored.root_cause_id = created.id
            await self._incidents.update(stored)
        return created

    async def confirm(
        self,
        organization_id: UUID,
        root_cause_id: UUID,
        *,
        confirmed_by: str,
    ) -> IncidentRootCause:
        """Confirm a finding, upgrading it from hypothesis to established cause."""
        row = await self._root_causes.require_in_org(organization_id, root_cause_id)
        row.is_confirmed = True
        row.confirmed_by = confirmed_by
        updated = await self._root_causes.update(row)

        incident = await self._incidents.require_in_org(organization_id, updated.incident_id)
        incident.root_cause_id = updated.id
        await self._incidents.update(incident)
        return updated

    async def list_for_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> list[IncidentRootCause]:
        """Every finding for one incident, in the order they were recorded."""
        await self._incidents.require_in_org(organization_id, incident_id)
        return await self._root_causes.list_for_incident(organization_id, incident_id)


class ProblemService:
    """Recurring-pattern problem records and their known errors."""

    def __init__(
        self,
        problems: ProblemRepository,
        known_errors: KnownErrorRepository,
        incidents: IncidentRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._problems = problems
        self._known_errors = known_errors
        self._incidents = incidents
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create(
        self,
        organization_id: UUID,
        *,
        title: str,
        description: str | None = None,
        incident_ids: list[UUID] | None = None,
        owner_id: str | None = None,
        actor_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ProblemRecord:
        """Record a recurring pattern as a problem, linking its incidents."""
        moment = now or datetime.now(UTC)
        existing = await self._problems.existing_references(organization_id)
        reference = _next_reference(existing)

        linked = [str(one) for one in (incident_ids or [])]
        created = await self._problems.create(
            ProblemRecord(
                organization_id=organization_id,
                reference=reference,
                title=title,
                description=description,
                status=ProblemStatus.OPEN,
                incident_ids=linked,
                incident_count=len(linked),
                owner_id=owner_id,
                identified_at=moment,
                created_by=actor_id,
            )
        )

        for incident_id in incident_ids or []:
            incident = await self._incidents.require_in_org(organization_id, incident_id)
            incident.problem_id = created.id
            await self._incidents.update(incident)

        await self._publish_event(
            ProblemCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "problem_id": str(created.id),
                    "reference": reference,
                    "incident_count": len(linked),
                },
            )
        )
        return created

    async def link_incident(
        self, organization_id: UUID, problem_id: UUID, incident_id: UUID
    ) -> ProblemRecord:
        """Attach one more incident to an existing problem."""
        problem = await self._problems.require_in_org(organization_id, problem_id)
        incident = await self._incidents.require_in_org(organization_id, incident_id)

        key = str(incident_id)
        if key not in problem.incident_ids:
            problem.incident_ids = [*problem.incident_ids, key]
            problem.incident_count = len(problem.incident_ids)
            await self._problems.update(problem)

        incident.problem_id = problem.id
        await self._incidents.update(incident)
        return problem

    async def transition(
        self,
        organization_id: UUID,
        problem_id: UUID,
        *,
        target: ProblemStatus,
        permanent_fix: str | None = None,
        now: datetime | None = None,
    ) -> ProblemRecord:
        """Move a problem through its lifecycle.

        Raises:
            ConflictError: If moving to ``RESOLVED`` without a stated fix
                -- a problem cannot be resolved by declaration alone;
                the permanent fix is the thing that makes it resolved.
        """
        moment = now or datetime.now(UTC)
        row = await self._problems.require_in_org(organization_id, problem_id)
        if target is ProblemStatus.RESOLVED and not (permanent_fix or row.permanent_fix):
            raise ConflictError(
                f"Problem {row.reference} cannot be marked resolved without a stated permanent fix."
            )
        row.status = target
        if permanent_fix:
            row.permanent_fix = permanent_fix
        if target is ProblemStatus.RESOLVED:
            row.resolved_at = moment
        if target is ProblemStatus.CLOSED:
            row.closed_at = moment
        return await self._problems.update(row)

    async def record_known_error(
        self,
        organization_id: UUID,
        problem_id: UUID,
        *,
        title: str,
        root_cause_summary: str,
        workaround: str | None = None,
        affected_versions: list[str] | None = None,
        recorded_by: str | None = None,
        now: datetime | None = None,
    ) -> KnownError:
        """Record a known error against a problem.

        A problem becomes a known error the moment its root cause is
        understood, whether or not a permanent fix exists yet -- see
        ``app/models/rca.py`` for why this is a distinct status rather
        than waiting for ``RESOLVED``.
        """
        moment = now or datetime.now(UTC)
        problem = await self._problems.require_in_org(organization_id, problem_id)
        problem.status = ProblemStatus.KNOWN_ERROR
        await self._problems.update(problem)

        return await self._known_errors.create(
            KnownError(
                organization_id=organization_id,
                problem_id=problem_id,
                title=title,
                root_cause_summary=root_cause_summary,
                workaround=workaround,
                affected_versions=list(affected_versions or []),
                is_active=True,
                recorded_by=recorded_by,
                recorded_at=moment,
                created_by=None,
            )
        )

    async def retire_known_error(
        self, organization_id: UUID, known_error_id: UUID, *, now: datetime | None = None
    ) -> KnownError:
        """Mark a known error retired -- the permanent fix has shipped."""
        row = await self._known_errors.require_in_org(organization_id, known_error_id)
        row.is_active = False
        row.retired_at = now or datetime.now(UTC)
        return await self._known_errors.update(row)

    async def get(self, organization_id: UUID, problem_id: UUID) -> ProblemRecord:
        """One problem.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._problems.require_in_org(organization_id, problem_id)

    async def list_problems(
        self,
        organization_id: UUID,
        *,
        status: ProblemStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ProblemRecord]:
        """Problems matching a caller's filters."""
        return await self._problems.list_filtered(
            organization_id, status=status, limit=limit, offset=offset
        )

    async def list_active_known_errors(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[KnownError]:
        """Every active known error -- the 03:00 triage lookup."""
        return await self._known_errors.list_active(organization_id, limit=limit, offset=offset)


__all__ = ["ProblemService", "RootCauseService"]
