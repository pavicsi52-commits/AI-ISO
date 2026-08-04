"""Root cause, problem management, and known error endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ProblemSvc, RootCauseSvc
from app.models.enums import AuditAction, ProblemStatus
from app.schemas.incident import (
    KnownErrorCreateRequest,
    KnownErrorResponse,
    ProblemCreateRequest,
    ProblemLinkIncidentRequest,
    ProblemResponse,
    ProblemTransitionRequest,
    RootCauseConfirmRequest,
    RootCauseRecordRequest,
    RootCauseResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Root Cause & Problems"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- root cause ---------------------------------------------------------------


@router.post(
    "/incidents/{incident_id}/root-cause",
    response_model=SuccessResponse[RootCauseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a root cause finding",
)
async def record_root_cause(
    organization_id: UUID,
    incident_id: UUID,
    body: RootCauseRecordRequest,
    root_causes: RootCauseSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RootCauseResponse]:
    """Record a finding. Every finding is kept, not just the latest."""
    created = await root_causes.record(
        organization_id,
        incident_id,
        method=body.method,
        summary=body.summary,
        contributing_factors=body.contributing_factors,
        confidence=body.confidence,
        is_confirmed=body.is_confirmed,
        evidence=body.evidence,
        recorded_by=body.recorded_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.ROOT_CAUSE_RECORDED,
        entity_type="incident",
        entity_id=incident_id,
        actor_id=str(caller),
        summary=f"Recorded a root cause finding via {body.method!s}.",
    )
    return SuccessResponse(
        meta=_meta(), data=RootCauseResponse.model_validate(created), message="Root cause recorded."
    )


@router.get(
    "/incidents/{incident_id}/root-cause",
    response_model=SuccessResponse[list[RootCauseResponse]],
    summary="Read every root cause finding for an incident",
)
async def list_root_causes(
    organization_id: UUID, incident_id: UUID, root_causes: RootCauseSvc
) -> SuccessResponse[list[RootCauseResponse]]:
    """Every finding, in the order they were recorded."""
    rows = await root_causes.list_for_incident(organization_id, incident_id)
    return SuccessResponse(
        meta=_meta(),
        data=[RootCauseResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} finding(s).",
    )


@router.post(
    "/root-cause/{root_cause_id}/confirm",
    response_model=SuccessResponse[RootCauseResponse],
    summary="Confirm a root cause finding",
)
async def confirm_root_cause(
    organization_id: UUID,
    root_cause_id: UUID,
    body: RootCauseConfirmRequest,
    root_causes: RootCauseSvc,
) -> SuccessResponse[RootCauseResponse]:
    """Upgrade a finding from hypothesis to established cause."""
    updated = await root_causes.confirm(
        organization_id, root_cause_id, confirmed_by=body.confirmed_by
    )
    return SuccessResponse(
        meta=_meta(),
        data=RootCauseResponse.model_validate(updated),
        message="Root cause confirmed.",
    )


# ---- problems -------------------------------------------------------------------


@router.post(
    "/problems",
    response_model=SuccessResponse[ProblemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a recurring pattern as a problem",
)
async def create_problem(
    organization_id: UUID,
    body: ProblemCreateRequest,
    problems: ProblemSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ProblemResponse]:
    """Create a problem, linking whichever incidents are already known to share it."""
    created = await problems.create(
        organization_id,
        title=body.title,
        description=body.description,
        incident_ids=body.incident_ids,
        owner_id=body.owner_id,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.PROBLEM_CREATED,
        entity_type="problem",
        entity_id=created.id,
        entity_reference=created.reference,
        actor_id=str(caller),
        summary=f"Created problem {created.reference}: {body.title!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ProblemResponse.model_validate(created), message="Problem recorded."
    )


@router.get(
    "/problems", response_model=SuccessResponse[list[ProblemResponse]], summary="List problems"
)
async def list_problems(
    organization_id: UUID,
    problems: ProblemSvc,
    status_filter: Annotated[ProblemStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ProblemResponse]]:
    """Problems matching a caller's filters."""
    rows = await problems.list_problems(
        organization_id, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        meta=_meta(),
        data=[ProblemResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} problem(s).",
    )


@router.get(
    "/problems/{problem_id}",
    response_model=SuccessResponse[ProblemResponse],
    summary="Read one problem",
)
async def get_problem(
    organization_id: UUID, problem_id: UUID, problems: ProblemSvc
) -> SuccessResponse[ProblemResponse]:
    """One problem."""
    found = await problems.get(organization_id, problem_id)
    return SuccessResponse(
        meta=_meta(), data=ProblemResponse.model_validate(found), message="Problem read."
    )


@router.post(
    "/problems/{problem_id}/link-incident",
    response_model=SuccessResponse[ProblemResponse],
    summary="Attach one more incident to an existing problem",
)
async def link_incident(
    organization_id: UUID,
    problem_id: UUID,
    body: ProblemLinkIncidentRequest,
    problems: ProblemSvc,
) -> SuccessResponse[ProblemResponse]:
    """Link one more incident."""
    updated = await problems.link_incident(organization_id, problem_id, body.incident_id)
    return SuccessResponse(
        meta=_meta(), data=ProblemResponse.model_validate(updated), message="Incident linked."
    )


@router.put(
    "/problems/{problem_id}/transition",
    response_model=SuccessResponse[ProblemResponse],
    summary="Move a problem through its lifecycle",
)
async def transition_problem(
    organization_id: UUID,
    problem_id: UUID,
    body: ProblemTransitionRequest,
    problems: ProblemSvc,
) -> SuccessResponse[ProblemResponse]:
    """Change status. Refuses moving to RESOLVED without a stated permanent fix."""
    updated = await problems.transition(
        organization_id, problem_id, target=body.status, permanent_fix=body.permanent_fix
    )
    return SuccessResponse(
        meta=_meta(),
        data=ProblemResponse.model_validate(updated),
        message="Problem status changed.",
    )


# ---- known errors ---------------------------------------------------------------


@router.post(
    "/problems/{problem_id}/known-errors",
    response_model=SuccessResponse[KnownErrorResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a known error against a problem",
)
async def record_known_error(
    organization_id: UUID,
    problem_id: UUID,
    body: KnownErrorCreateRequest,
    problems: ProblemSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[KnownErrorResponse]:
    """Record a known error. Also moves the problem to KNOWN_ERROR status."""
    created = await problems.record_known_error(
        organization_id,
        problem_id,
        title=body.title,
        root_cause_summary=body.root_cause_summary,
        workaround=body.workaround,
        affected_versions=body.affected_versions,
        recorded_by=body.recorded_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.KNOWN_ERROR_RECORDED,
        entity_type="problem",
        entity_id=problem_id,
        actor_id=str(caller),
        summary=f"Recorded known error: {body.title!r}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=KnownErrorResponse.model_validate(created),
        message="Known error recorded.",
    )


@router.get(
    "/known-errors",
    response_model=SuccessResponse[list[KnownErrorResponse]],
    summary="List active known errors",
)
async def list_active_known_errors(
    organization_id: UUID,
    problems: ProblemSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[KnownErrorResponse]]:
    """Every active known error -- the 03:00 triage lookup."""
    rows = await problems.list_active_known_errors(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        meta=_meta(),
        data=[KnownErrorResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} active known error(s).",
    )


@router.post(
    "/known-errors/{known_error_id}/retire",
    response_model=SuccessResponse[KnownErrorResponse],
    summary="Retire a known error",
)
async def retire_known_error(
    organization_id: UUID, known_error_id: UUID, problems: ProblemSvc
) -> SuccessResponse[KnownErrorResponse]:
    """Mark a known error retired -- the permanent fix has shipped."""
    updated = await problems.retire_known_error(organization_id, known_error_id)
    return SuccessResponse(
        meta=_meta(),
        data=KnownErrorResponse.model_validate(updated),
        message="Known error retired.",
    )


__all__ = ["router"]
