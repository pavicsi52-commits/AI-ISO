"""Choosing and applying an assignment, given a roster.

Wraps ``app/assignment/engine.py``. The roster itself -- who is on call,
who has which skills -- is supplied by the caller rather than resolved
here, because this service does not own on-call schedules or skill
tags; those belong to whatever system of record an organization already
uses for them, and hard-coding a lookup here would make this service
authoritative over data it has no business owning.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.assignment.engine import AssignmentDecision, Responder, assign
from app.models.incident import Incident
from app.repositories.incident import IncidentRepository
from app.services.incident import IncidentService

logger = get_logger("app.services.assignment")


class AssignmentService:
    """Decides who an incident should go to, and applies the decision."""

    def __init__(self, incidents: IncidentRepository, incident_service: IncidentService) -> None:
        self._incidents = incidents
        self._incident_service = incident_service

    async def roster_with_current_load(
        self, organization_id: UUID, roster: list[Responder]
    ) -> list[Responder]:
        """Refresh a caller-supplied roster's load from this service's own data.

        The roster's *identity* (who exists, their skills, their on-call
        status) comes from the caller; only *load* is something this
        service can answer authoritatively, since it owns the incident
        table the load is counted from.
        """
        refreshed: list[Responder] = []
        for one in roster:
            count = await self._incidents.count_open_for_assignee(organization_id, one.responder_id)
            refreshed.append(
                Responder(
                    responder_id=one.responder_id,
                    team=one.team,
                    skills=one.skills,
                    open_incident_count=count,
                    is_on_call=one.is_on_call,
                    is_available=one.is_available,
                )
            )
        return refreshed

    async def decide_and_apply(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        roster: list[Responder],
        required_skills: frozenset[str] = frozenset(),
        prefer_on_call: bool = True,
        actor_id: UUID | None = None,
    ) -> tuple[Incident, AssignmentDecision]:
        """Choose a responder from *roster* and assign the incident to them.

        Raises:
            ValidationError: If nobody in *roster* is eligible.
        """
        live_roster = await self.roster_with_current_load(organization_id, roster)
        decision = assign(
            live_roster, required_skills=required_skills, prefer_on_call=prefer_on_call
        )
        if decision is None:
            raise ValidationError("No eligible responder is available to assign this incident to.")

        updated = await self._incident_service.assign(
            organization_id,
            incident_id,
            assignee_id=decision.responder.responder_id,
            assignee_team=decision.responder.team,
            method=decision.method,
            reason=decision.reason,
            actor_id=actor_id,
        )
        return updated, decision


__all__ = ["AssignmentService"]
