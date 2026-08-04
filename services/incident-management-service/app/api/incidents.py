"""Incident, SLA, escalation, assignment, and impact endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AssignmentSvc,
    AuditSvc,
    CurrentUserId,
    EscalationSvc,
    ImpactSvc,
    IncidentSvc,
    SlaSvc,
)
from app.assignment.engine import Responder
from app.impact.engine import ServiceImpact
from app.models.enums import (
    AuditAction,
    IncidentCategory,
    IncidentPriority,
    IncidentStatus,
)
from app.schemas.incident import (
    EscalationCancelRequest,
    EscalationResponse,
    ImpactAssessRequest,
    ImpactResponse,
    IncidentAssignRequest,
    IncidentAutoAssignRequest,
    IncidentCreateRequest,
    IncidentMergeRequest,
    IncidentResponse,
    IncidentTransitionRequest,
    ManualEscalationRequest,
    SlaPauseRequest,
    SlaResponse,
    TimelineEntryResponse,
    TimelineNoteRequest,
    WorklogCreateRequest,
    WorklogResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[IncidentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Open a new incident",
)
async def create_incident(
    organization_id: UUID,
    body: IncidentCreateRequest,
    incidents: IncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[IncidentResponse]:
    """Open an incident, or correlate onto an existing open one with the same fingerprint."""
    created, is_new = await incidents.create(
        organization_id,
        title=body.title,
        description=body.description,
        source=body.source,
        source_reference=body.source_reference,
        category=body.category,
        priority=body.priority,
        correlation_key=body.correlation_key,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.INCIDENT_CREATED,
        entity_type="incident",
        entity_id=created.id,
        entity_reference=created.reference,
        actor_id=str(caller),
        summary=(
            f"Opened {created.reference}: {body.title!r}."
            if is_new
            else f"Correlated onto existing incident {created.reference}: {body.title!r}."
        ),
    )
    message = "Incident opened." if is_new else "Correlated onto an existing open incident."
    return SuccessResponse(
        meta=_meta(),
        data=IncidentResponse.model_validate(created),
        message=message,
    )


@router.get("", response_model=SuccessResponse[list[IncidentResponse]], summary="List incidents")
async def list_incidents(
    organization_id: UUID,
    incidents: IncidentSvc,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    priority: IncidentPriority | None = None,
    category: IncidentCategory | None = None,
    assignee_id: str | None = None,
    is_major: bool | None = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[IncidentResponse]]:
    """Incidents matching a caller's filters."""
    rows = await incidents.list_incidents(
        organization_id,
        status=status_filter,
        priority=priority,
        category=category,
        assignee_id=assignee_id,
        is_major=is_major,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[IncidentResponse.model_validate(one) for one in rows],
        message=f"Found {len(rows)} incident(s).",
    )


@router.get(
    "/{incident_id}", response_model=SuccessResponse[IncidentResponse], summary="Read an incident"
)
async def get_incident(
    organization_id: UUID, incident_id: UUID, incidents: IncidentSvc
) -> SuccessResponse[IncidentResponse]:
    """One incident."""
    found = await incidents.get(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(), data=IncidentResponse.model_validate(found), message="Incident read."
    )


@router.put(
    "/{incident_id}/transition",
    response_model=SuccessResponse[IncidentResponse],
    summary="Move an incident through its lifecycle",
)
async def transition_incident(
    organization_id: UUID,
    incident_id: UUID,
    body: IncidentTransitionRequest,
    incidents: IncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[IncidentResponse]:
    """Change status. Refuses moves the lifecycle does not allow."""
    updated = await incidents.transition(
        organization_id, incident_id, target=body.status, note=body.note, actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.STATUS_CHANGED,
        entity_type="incident",
        entity_id=incident_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Moved {updated.reference} to {body.status!s}.",
    )
    return SuccessResponse(
        meta=_meta(), data=IncidentResponse.model_validate(updated), message="Status changed."
    )


@router.post(
    "/{incident_id}/assign",
    response_model=SuccessResponse[IncidentResponse],
    summary="Assign an incident to a named responder",
)
async def assign_incident(
    organization_id: UUID,
    incident_id: UUID,
    body: IncidentAssignRequest,
    incidents: IncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[IncidentResponse]:
    """Assign directly to a named responder."""
    updated = await incidents.assign(
        organization_id,
        incident_id,
        assignee_id=body.assignee_id,
        assignee_team=body.assignee_team,
        method=body.method,
        reason=body.reason,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.ASSIGNED,
        entity_type="incident",
        entity_id=incident_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Assigned {updated.reference} to {body.assignee_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=IncidentResponse.model_validate(updated), message="Incident assigned."
    )


@router.post(
    "/{incident_id}/auto-assign",
    response_model=SuccessResponse[IncidentResponse],
    summary="Assign an incident by choosing from a supplied roster",
)
async def auto_assign_incident(
    organization_id: UUID,
    incident_id: UUID,
    body: IncidentAutoAssignRequest,
    assignment: AssignmentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[IncidentResponse]:
    """Choose a responder from *roster* and assign the incident to them."""
    roster = [
        Responder(
            responder_id=one.responder_id,
            team=one.team,
            skills=frozenset(one.skills),
            is_on_call=one.is_on_call,
            is_available=one.is_available,
        )
        for one in body.roster
    ]
    updated, decision = await assignment.decide_and_apply(
        organization_id,
        incident_id,
        roster=roster,
        required_skills=frozenset(body.required_skills),
        prefer_on_call=body.prefer_on_call,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.ASSIGNED,
        entity_type="incident",
        entity_id=incident_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=(
            f"Auto-assigned {updated.reference} to {decision.responder.responder_id} "
            f"({decision.reason})."
        ),
    )
    return SuccessResponse(
        meta=_meta(),
        data=IncidentResponse.model_validate(updated),
        message="Incident auto-assigned.",
    )


@router.post(
    "/{incident_id}/merge",
    response_model=SuccessResponse[IncidentResponse],
    summary="Merge one incident into another",
)
async def merge_incident(
    organization_id: UUID,
    incident_id: UUID,
    body: IncidentMergeRequest,
    incidents: IncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[IncidentResponse]:
    """Merge *incident_id* into ``target_incident_id``."""
    updated = await incidents.merge(
        organization_id,
        source_incident_id=incident_id,
        target_incident_id=body.target_incident_id,
        reason=body.reason,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.INCIDENT_UPDATED,
        entity_type="incident",
        entity_id=incident_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Merged {updated.reference} into {body.target_incident_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=IncidentResponse.model_validate(updated), message="Incidents merged."
    )


@router.get(
    "/{incident_id}/timeline",
    response_model=SuccessResponse[list[TimelineEntryResponse]],
    summary="Read an incident's timeline",
)
async def get_timeline(
    organization_id: UUID, incident_id: UUID, incidents: IncidentSvc
) -> SuccessResponse[list[TimelineEntryResponse]]:
    """The full, append-only timeline, oldest first."""
    rows = await incidents.timeline(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[TimelineEntryResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} timeline entr(y/ies).",
    )


@router.post(
    "/{incident_id}/notes",
    response_model=SuccessResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="Add a note to an incident's timeline",
)
async def add_note(
    organization_id: UUID,
    incident_id: UUID,
    body: TimelineNoteRequest,
    incidents: IncidentSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict]:
    """Append a free-text note."""
    await incidents.add_note(organization_id, incident_id, summary=body.summary, actor_id=caller)
    return SuccessResponse(meta=_meta(), data={}, message="Note added.")


@router.post(
    "/{incident_id}/worklog",
    response_model=SuccessResponse[WorklogResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Log effort spent on an incident",
)
async def add_worklog(
    organization_id: UUID,
    incident_id: UUID,
    body: WorklogCreateRequest,
    incidents: IncidentSvc,
    caller: CurrentUserId,
) -> SuccessResponse[WorklogResponse]:
    """Record effort spent."""
    created = await incidents.add_worklog(
        organization_id,
        incident_id,
        note=body.note,
        kind=body.kind,
        minutes_spent=body.minutes_spent,
        author_id=caller,
    )
    return SuccessResponse(
        meta=_meta(), data=WorklogResponse.model_validate(created), message="Worklog entry added."
    )


@router.get(
    "/{incident_id}/worklog",
    response_model=SuccessResponse[list[WorklogResponse]],
    summary="Read an incident's worklog",
)
async def get_worklog(
    organization_id: UUID, incident_id: UUID, incidents: IncidentSvc
) -> SuccessResponse[list[WorklogResponse]]:
    """Every worklog entry, oldest first."""
    rows = await incidents.worklogs(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[WorklogResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} worklog entr(y/ies).",
    )


# ---- SLA --------------------------------------------------------------------


@router.get(
    "/{incident_id}/slas",
    response_model=SuccessResponse[list[SlaResponse]],
    summary="Read an incident's SLA clocks",
)
async def list_slas(
    organization_id: UUID, incident_id: UUID, slas: SlaSvc
) -> SuccessResponse[list[SlaResponse]]:
    """Every SLA clock on this incident."""
    rows = await slas.list_for_incident(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[SlaResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} SLA clock(s).",
    )


@router.post(
    "/slas/{sla_id}/pause",
    response_model=SuccessResponse[SlaResponse],
    summary="Pause a running SLA clock",
)
async def pause_sla(
    organization_id: UUID, sla_id: UUID, body: SlaPauseRequest, slas: SlaSvc
) -> SuccessResponse[SlaResponse]:
    """Pause a running clock."""
    updated = await slas.pause(organization_id, sla_id, reason=body.reason)
    return SuccessResponse(
        meta=_meta(), data=SlaResponse.model_validate(updated), message="SLA clock paused."
    )


@router.post(
    "/slas/{sla_id}/resume",
    response_model=SuccessResponse[SlaResponse],
    summary="Resume a paused SLA clock",
)
async def resume_sla(
    organization_id: UUID, sla_id: UUID, slas: SlaSvc
) -> SuccessResponse[SlaResponse]:
    """Resume a paused clock."""
    updated = await slas.resume(organization_id, sla_id)
    return SuccessResponse(
        meta=_meta(), data=SlaResponse.model_validate(updated), message="SLA clock resumed."
    )


# ---- escalation ---------------------------------------------------------------


@router.get(
    "/{incident_id}/escalations",
    response_model=SuccessResponse[list[EscalationResponse]],
    summary="Read an incident's escalations",
)
async def list_escalations(
    organization_id: UUID, incident_id: UUID, escalations: EscalationSvc
) -> SuccessResponse[list[EscalationResponse]]:
    """Every escalation on this incident."""
    rows = await escalations.list_for_incident(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[EscalationResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} escalation(s).",
    )


@router.post(
    "/{incident_id}/escalate",
    response_model=SuccessResponse[EscalationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Escalate an incident manually",
)
async def escalate_manually(
    organization_id: UUID,
    incident_id: UUID,
    body: ManualEscalationRequest,
    escalations: EscalationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[EscalationResponse]:
    """Escalate to a named target, outside any policy ladder."""
    created = await escalations.escalate_manually(
        organization_id,
        incident_id,
        target_id=body.target_id,
        reason=body.reason,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.ESCALATED,
        entity_type="incident",
        entity_id=incident_id,
        actor_id=str(caller),
        summary=f"Manually escalated to {body.target_id}: {body.reason}",
    )
    return SuccessResponse(
        meta=_meta(), data=EscalationResponse.model_validate(created), message="Incident escalated."
    )


@router.post(
    "/escalations/{escalation_id}/acknowledge",
    response_model=SuccessResponse[EscalationResponse],
    summary="Acknowledge a fired escalation",
)
async def acknowledge_escalation(
    organization_id: UUID, escalation_id: UUID, escalations: EscalationSvc
) -> SuccessResponse[EscalationResponse]:
    """Acknowledge one escalation."""
    updated = await escalations.acknowledge(organization_id, escalation_id)
    return SuccessResponse(
        meta=_meta(),
        data=EscalationResponse.model_validate(updated),
        message="Escalation acknowledged.",
    )


@router.post(
    "/escalations/{escalation_id}/cancel",
    response_model=SuccessResponse[EscalationResponse],
    summary="Cancel a pending or triggered escalation",
)
async def cancel_escalation(
    organization_id: UUID,
    escalation_id: UUID,
    body: EscalationCancelRequest,
    escalations: EscalationSvc,
) -> SuccessResponse[EscalationResponse]:
    """Cancel one escalation."""
    updated = await escalations.cancel(organization_id, escalation_id, reason=body.reason)
    return SuccessResponse(
        meta=_meta(),
        data=EscalationResponse.model_validate(updated),
        message="Escalation cancelled.",
    )


# ---- impact -----------------------------------------------------------------


@router.post(
    "/{incident_id}/impact",
    response_model=SuccessResponse[ImpactResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a fresh impact assessment",
)
async def assess_impact(
    organization_id: UUID,
    incident_id: UUID,
    body: ImpactAssessRequest,
    impact: ImpactSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ImpactResponse]:
    """Assess impact and derive the incident's risk level."""
    created = await impact.assess(
        organization_id,
        incident_id,
        services=[
            ServiceImpact(one.service_name, one.impact_level, one.is_root) for one in body.services
        ],
        assets=[
            (one.asset_id or one.asset_name, one.asset_name, one.impact_level, one.detail)
            for one in body.assets
        ],
        business_impact=body.business_impact,
        customer_impact=body.customer_impact,
        affected_users_estimate=body.affected_users_estimate,
        assessed_by=body.assessed_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.INCIDENT_UPDATED,
        entity_type="incident",
        entity_id=incident_id,
        actor_id=str(caller),
        summary=f"Recorded an impact assessment ({len(body.services)} service(s)).",
    )
    return SuccessResponse(
        meta=_meta(), data=ImpactResponse.model_validate(created), message="Impact assessed."
    )


@router.get(
    "/{incident_id}/impact",
    response_model=SuccessResponse[list[ImpactResponse]],
    summary="Read an incident's impact history",
)
async def get_impact_history(
    organization_id: UUID, incident_id: UUID, impact: ImpactSvc
) -> SuccessResponse[list[ImpactResponse]]:
    """Every assessment, newest first."""
    rows = await impact.history(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ImpactResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} assessment(s).",
    )


__all__ = ["router"]
