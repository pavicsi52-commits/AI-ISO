"""Major incident declaration and war room endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, MajorIncidentSvc
from app.models.enums import AuditAction
from app.schemas.incident import (
    MajorIncidentApproveClosureRequest,
    MajorIncidentDeclareRequest,
    MajorIncidentResponse,
    MajorIncidentStatusUpdateRequest,
    WarRoomLeaveRequest,
    WarRoomNoteRequest,
    WarRoomParticipantResponse,
    WarRoomResponse,
    WarRoomRoleRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/major-incidents", tags=["Major Incidents"])
war_room_router = APIRouter(prefix="/war-rooms", tags=["War Rooms"])
"""A separate router with its own top-level prefix, not nested under
``/major-incidents/{incident_id}``. A war room is addressed by its own
id, not an incident's, and nesting it under a path that already has a
``{incident_id}`` segment would make ``/major-incidents/war-rooms/<id>``
ambiguous with ``/major-incidents/{incident_id}`` -- resolved correctly
by UUID-coercion failure, but a hazard not worth carrying when a
distinct prefix removes it outright.
"""


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/{incident_id}/declare",
    response_model=SuccessResponse[MajorIncidentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Declare an incident major and open its war room",
)
async def declare_major_incident(
    organization_id: UUID,
    incident_id: UUID,
    body: MajorIncidentDeclareRequest,
    major_incidents: MajorIncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[MajorIncidentResponse]:
    """Declare major, opening the war room in the same call."""
    declaration, _war_room = await major_incidents.declare(
        organization_id,
        incident_id,
        reason=body.reason,
        incident_commander_id=body.incident_commander_id,
        stakeholder_ids=body.stakeholder_ids,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.MAJOR_INCIDENT_DECLARED,
        entity_type="incident",
        entity_id=incident_id,
        actor_id=str(caller),
        summary=f"Declared incident {incident_id} major: {body.reason}",
    )
    return SuccessResponse(
        meta=_meta(),
        data=MajorIncidentResponse.model_validate(declaration),
        message="Major incident declared.",
    )


@router.get(
    "",
    response_model=SuccessResponse[list[MajorIncidentResponse]],
    summary="List active major incidents",
)
async def list_active_major_incidents(
    organization_id: UUID, major_incidents: MajorIncidentSvc
) -> SuccessResponse[list[MajorIncidentResponse]]:
    """Every major incident not yet stood down."""
    rows = await major_incidents.list_active(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[MajorIncidentResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} active major incident(s).",
    )


@router.get(
    "/{incident_id}",
    response_model=SuccessResponse[MajorIncidentResponse | None],
    summary="Read the major incident declaration for an incident",
)
async def get_major_incident(
    organization_id: UUID, incident_id: UUID, major_incidents: MajorIncidentSvc
) -> SuccessResponse[MajorIncidentResponse | None]:
    """The declaration for one incident, if it has been declared major."""
    declaration = await major_incidents.get_declaration(organization_id, incident_id)
    data = MajorIncidentResponse.model_validate(declaration) if declaration else None
    return SuccessResponse(
        meta=_meta(),
        data=data,
        message="Declaration found." if declaration else "No major incident declaration exists.",
    )


@router.post(
    "/{major_incident_id}/status-update",
    response_model=SuccessResponse[MajorIncidentResponse],
    summary="Record a stakeholder status update",
)
async def record_status_update(
    organization_id: UUID,
    major_incident_id: UUID,
    body: MajorIncidentStatusUpdateRequest,
    major_incidents: MajorIncidentSvc,
) -> SuccessResponse[MajorIncidentResponse]:
    """Record that a stakeholder update went out."""
    updated = await major_incidents.record_status_update(
        organization_id, major_incident_id, summary=body.summary
    )
    return SuccessResponse(
        meta=_meta(),
        data=MajorIncidentResponse.model_validate(updated),
        message="Status update recorded.",
    )


@router.post(
    "/{major_incident_id}/approve-closure",
    response_model=SuccessResponse[MajorIncidentResponse],
    summary="Approve closing out a major incident",
)
async def approve_closure(
    organization_id: UUID,
    major_incident_id: UUID,
    body: MajorIncidentApproveClosureRequest,
    major_incidents: MajorIncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[MajorIncidentResponse]:
    """Record executive approval to close out a major incident.

    Refuses unless the underlying incident has at least resolved.
    """
    updated = await major_incidents.approve_closure(
        organization_id, major_incident_id, approved_by=body.approved_by
    )
    await audit.record(
        organization_id,
        action=AuditAction.MAJOR_INCIDENT_DECLARED,
        entity_type="major_incident",
        entity_id=major_incident_id,
        actor_id=str(caller),
        summary=f"Closure approved by {body.approved_by}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=MajorIncidentResponse.model_validate(updated),
        message="Closure approved.",
    )


# ---- war rooms ----------------------------------------------------------------


@war_room_router.get(
    "/{war_room_id}",
    response_model=SuccessResponse[WarRoomResponse],
    summary="Read a war room",
)
async def get_war_room(
    organization_id: UUID, war_room_id: UUID, major_incidents: MajorIncidentSvc
) -> SuccessResponse[WarRoomResponse]:
    """One war room."""
    found = await major_incidents.get_war_room(organization_id, war_room_id)
    return SuccessResponse(
        meta=_meta(), data=WarRoomResponse.model_validate(found), message="War room read."
    )


@war_room_router.post(
    "/{war_room_id}/participants",
    response_model=SuccessResponse[WarRoomParticipantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a participant to a war room",
)
async def add_participant(
    organization_id: UUID,
    war_room_id: UUID,
    body: WarRoomRoleRequest,
    major_incidents: MajorIncidentSvc,
) -> SuccessResponse[WarRoomParticipantResponse]:
    """Add a participant, in a given role.

    Refuses to double-assign a singleton role
    (incident commander, communication lead, technical lead, business
    lead) to two different people at once.
    """
    created = await major_incidents.assign_role(
        organization_id, war_room_id, participant_id=body.participant_id, role=body.role
    )
    return SuccessResponse(
        meta=_meta(),
        data=WarRoomParticipantResponse.model_validate(created),
        message="Participant added.",
    )


@war_room_router.get(
    "/{war_room_id}/participants",
    response_model=SuccessResponse[list[WarRoomParticipantResponse]],
    summary="List a war room's participants",
)
async def list_participants(
    organization_id: UUID, war_room_id: UUID, major_incidents: MajorIncidentSvc
) -> SuccessResponse[list[WarRoomParticipantResponse]]:
    """Everyone who has ever been in the room, including those who left."""
    rows = await major_incidents.participants(organization_id, war_room_id)
    return SuccessResponse(
        meta=_meta(),
        data=[WarRoomParticipantResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} participant(s).",
    )


@war_room_router.post(
    "/{war_room_id}/leave",
    response_model=SuccessResponse[dict],
    summary="Mark a participant as having left",
)
async def leave_war_room(
    organization_id: UUID,
    war_room_id: UUID,
    body: WarRoomLeaveRequest,
    major_incidents: MajorIncidentSvc,
) -> SuccessResponse[dict]:
    """Mark one participant as having left."""
    await major_incidents.leave(organization_id, war_room_id, participant_id=body.participant_id)
    return SuccessResponse(meta=_meta(), data={}, message="Participant left.")


@war_room_router.post(
    "/{war_room_id}/notes",
    response_model=SuccessResponse[WarRoomResponse],
    summary="Append to a war room's shared notes",
)
async def add_shared_note(
    organization_id: UUID,
    war_room_id: UUID,
    body: WarRoomNoteRequest,
    major_incidents: MajorIncidentSvc,
) -> SuccessResponse[WarRoomResponse]:
    """Append a note to the shared notes."""
    updated = await major_incidents.add_shared_note(organization_id, war_room_id, note=body.note)
    return SuccessResponse(
        meta=_meta(), data=WarRoomResponse.model_validate(updated), message="Note appended."
    )


@war_room_router.post(
    "/{war_room_id}/stand-down",
    response_model=SuccessResponse[WarRoomResponse],
    summary="Close a war room",
)
async def stand_down(
    organization_id: UUID,
    war_room_id: UUID,
    major_incidents: MajorIncidentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[WarRoomResponse]:
    """Close the war room."""
    updated = await major_incidents.stand_down(
        organization_id, war_room_id, stood_down_by=str(caller)
    )
    await audit.record(
        organization_id,
        action=AuditAction.WAR_ROOM_CLOSED,
        entity_type="war_room",
        entity_id=war_room_id,
        actor_id=str(caller),
        summary=f"War room {war_room_id} stood down.",
    )
    return SuccessResponse(
        meta=_meta(), data=WarRoomResponse.model_validate(updated), message="War room stood down."
    )


__all__ = ["router", "war_room_router"]
