"""Change, relationship, risk assessment, and approval endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import ApprovalSvc, AuditSvc, ChangeSvc, CurrentUserId, RiskSvc
from app.models.enums import AuditAction, ChangeCategory, ChangePriority, ChangeStatus
from app.risk.engine import RiskDimensions
from app.schemas.change import (
    ApprovalDecideRequest,
    ApprovalDelegateRequest,
    ApprovalRequestPayload,
    ApprovalResponse,
    ChangeCreateRequest,
    ChangeRelationshipRequest,
    ChangeRelationshipResponse,
    ChangeResponse,
    ChangeScheduleRequest,
    ChangeUpdateRequest,
    RiskAssessmentResponse,
    RiskAssessRequest,
    RiskOverrideRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/changes", tags=["Changes"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[ChangeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Open a new change request",
)
async def create_change(
    organization_id: UUID,
    body: ChangeCreateRequest,
    changes: ChangeSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Open a new change, in ``DRAFT``."""
    created = await changes.create(
        organization_id,
        title=body.title,
        requester_id=body.requester_id,
        description=body.description,
        business_justification=body.business_justification,
        business_owner_id=body.business_owner_id,
        technical_owner_id=body.technical_owner_id,
        category=body.category,
        change_type=body.change_type,
        priority=body.priority,
        affected_assets=body.affected_assets,
        affected_services=body.affected_services,
        affected_applications=body.affected_applications,
        implementation_plan=body.implementation_plan,
        validation_plan=body.validation_plan,
        rollback_plan=body.rollback_plan,
        incident_id=body.incident_id,
        problem_id=body.problem_id,
        known_error_id=body.known_error_id,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CHANGE_CREATED,
        entity_type="change",
        entity_id=created.id,
        entity_reference=created.reference,
        actor_id=str(caller),
        summary=f"Opened {created.reference}: {body.title!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(created), message="Change opened."
    )


@router.get("", response_model=SuccessResponse[list[ChangeResponse]], summary="List changes")
async def list_changes(
    organization_id: UUID,
    changes: ChangeSvc,
    status_filter: Annotated[ChangeStatus | None, Query(alias="status")] = None,
    priority: ChangePriority | None = None,
    category: ChangeCategory | None = None,
    technical_owner_id: Annotated[str | None, Query(max_length=255)] = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ChangeResponse]]:
    """Changes matching a caller's filters."""
    rows = await changes.list_changes(
        organization_id,
        status=status_filter,
        priority=priority,
        category=category,
        technical_owner_id=technical_owner_id,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[ChangeResponse.model_validate(one) for one in rows],
        message=f"Found {len(rows)} change(s).",
    )


@router.get(
    "/{change_id}", response_model=SuccessResponse[ChangeResponse], summary="Read one change"
)
async def get_change(
    organization_id: UUID, change_id: UUID, changes: ChangeSvc
) -> SuccessResponse[ChangeResponse]:
    """One change."""
    found = await changes.get(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(found), message="Change read."
    )


@router.put(
    "/{change_id}", response_model=SuccessResponse[ChangeResponse], summary="Edit a draft change"
)
async def update_change(
    organization_id: UUID,
    change_id: UUID,
    body: ChangeUpdateRequest,
    changes: ChangeSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Edit a change's own content. Refuses once it has left ``DRAFT``."""
    updated = await changes.update(
        organization_id,
        change_id,
        actor_id=caller,
        **body.model_dump(exclude_unset=True),
    )
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(updated), message="Change updated."
    )


@router.post(
    "/{change_id}/submit",
    response_model=SuccessResponse[ChangeResponse],
    summary="Submit a change for risk assessment and approval",
)
async def submit_change(
    organization_id: UUID,
    change_id: UUID,
    changes: ChangeSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Submit a draft change."""
    updated = await changes.submit(organization_id, change_id, actor_id=caller)
    await audit.record(
        organization_id,
        action=AuditAction.CHANGE_SUBMITTED,
        entity_type="change",
        entity_id=change_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Submitted {updated.reference}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(updated), message="Change submitted."
    )


@router.post(
    "/{change_id}/schedule",
    response_model=SuccessResponse[ChangeResponse],
    summary="Book a change into a maintenance window",
)
async def schedule_change(
    organization_id: UUID,
    change_id: UUID,
    body: ChangeScheduleRequest,
    changes: ChangeSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Schedule an approved change."""
    updated = await changes.schedule(
        organization_id,
        change_id,
        calendar_entry_id=body.calendar_entry_id,
        scheduled_start_at=body.scheduled_start_at,
        scheduled_end_at=body.scheduled_end_at,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CHANGE_SCHEDULED,
        entity_type="change",
        entity_id=change_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Scheduled {updated.reference} for {body.scheduled_start_at.isoformat()}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(updated), message="Change scheduled."
    )


@router.post(
    "/{change_id}/cancel",
    response_model=SuccessResponse[ChangeResponse],
    summary="Cancel a change",
)
async def cancel_change(
    organization_id: UUID,
    change_id: UUID,
    changes: ChangeSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Cancel a change. A true dead end -- a change that needs to try again is a new change."""
    updated = await changes.transition(
        organization_id, change_id, target=ChangeStatus.CANCELLED, actor_id=caller
    )
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(updated), message="Change cancelled."
    )


@router.post(
    "/{change_id}/close",
    response_model=SuccessResponse[ChangeResponse],
    summary="Close a completed or rolled-back change",
)
async def close_change(
    organization_id: UUID,
    change_id: UUID,
    changes: ChangeSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChangeResponse]:
    """Close out a change."""
    updated = await changes.close(organization_id, change_id, actor_id=caller)
    return SuccessResponse(
        meta=_meta(), data=ChangeResponse.model_validate(updated), message="Change closed."
    )


# ---- relationships --------------------------------------------------------------


@router.post(
    "/{change_id}/relationships",
    response_model=SuccessResponse[ChangeRelationshipResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Relate one change to another",
)
async def link_relationship(
    organization_id: UUID,
    change_id: UUID,
    body: ChangeRelationshipRequest,
    changes: ChangeSvc,
) -> SuccessResponse[ChangeRelationshipResponse]:
    """Record how one change relates to another."""
    created = await changes.link_relationship(
        organization_id,
        change_id,
        related_change_id=body.related_change_id,
        kind=body.kind,
        note=body.note,
    )
    return SuccessResponse(
        meta=_meta(),
        data=ChangeRelationshipResponse.model_validate(created),
        message="Relationship recorded.",
    )


@router.get(
    "/{change_id}/relationships",
    response_model=SuccessResponse[list[ChangeRelationshipResponse]],
    summary="List a change's relationships",
)
async def list_relationships(
    organization_id: UUID,
    change_id: UUID,
    changes: ChangeSvc,
) -> SuccessResponse[list[ChangeRelationshipResponse]]:
    """Every relationship this change is the source side of."""
    rows = await changes.list_relationships(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ChangeRelationshipResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} relationship(s).",
    )


# ---- risk -------------------------------------------------------------------------


@router.post(
    "/{change_id}/risk-assessments",
    response_model=SuccessResponse[RiskAssessmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Score and record a risk assessment",
)
async def assess_risk(
    organization_id: UUID,
    change_id: UUID,
    body: RiskAssessRequest,
    risk: RiskSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RiskAssessmentResponse]:
    """Score a change's risk, advancing it to pending approval."""
    created = await risk.assess(
        organization_id,
        change_id,
        likelihood=body.likelihood,
        dimensions=RiskDimensions(**body.dimensions.model_dump()),
        assessed_by=body.assessed_by,
        manual_override=body.manual_override,
        override_reason=body.override_reason,
        override_by=body.override_by,
    )
    await audit.record(
        organization_id,
        action=AuditAction.RISK_ASSESSED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"Recorded a risk assessment: {created.risk_level!s}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=RiskAssessmentResponse.model_validate(created),
        message="Risk assessed.",
    )


@router.get(
    "/{change_id}/risk-assessments",
    response_model=SuccessResponse[list[RiskAssessmentResponse]],
    summary="List a change's risk assessments",
)
async def list_risk_assessments(
    organization_id: UUID,
    change_id: UUID,
    risk: RiskSvc,
) -> SuccessResponse[list[RiskAssessmentResponse]]:
    """Every assessment for one change, in the order recorded."""
    rows = await risk.list_for_change(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[RiskAssessmentResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} assessment(s).",
    )


@router.post(
    "/risk-assessments/{assessment_id}/override",
    response_model=SuccessResponse[RiskAssessmentResponse],
    summary="Override a risk assessment",
)
async def override_risk(
    organization_id: UUID,
    assessment_id: UUID,
    body: RiskOverrideRequest,
    risk: RiskSvc,
) -> SuccessResponse[RiskAssessmentResponse]:
    """Override a recorded assessment's banding."""
    updated = await risk.override(
        organization_id, assessment_id, override=body.override, reason=body.reason, by=body.by
    )
    return SuccessResponse(
        meta=_meta(),
        data=RiskAssessmentResponse.model_validate(updated),
        message="Risk assessment overridden.",
    )


# ---- approvals --------------------------------------------------------------------


@router.post(
    "/{change_id}/approvals",
    response_model=SuccessResponse[list[ApprovalResponse]],
    status_code=status.HTTP_201_CREATED,
    summary="Open a change's approval chain",
)
async def request_approvals(
    organization_id: UUID,
    change_id: UUID,
    body: ApprovalRequestPayload,
    approvals: ApprovalSvc,
) -> SuccessResponse[list[ApprovalResponse]]:
    """Open an approval chain for a change pending approval."""
    rows = await approvals.request_approvals(
        organization_id,
        change_id,
        policy=body.policy,
        approvers=[(one.approver_id, one.approver_role) for one in body.approvers],
    )
    return SuccessResponse(
        meta=_meta(),
        data=[ApprovalResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} approval step(s) opened.",
    )


@router.get(
    "/{change_id}/approvals",
    response_model=SuccessResponse[list[ApprovalResponse]],
    summary="List a change's approval steps",
)
async def list_approvals(
    organization_id: UUID,
    change_id: UUID,
    approvals: ApprovalSvc,
) -> SuccessResponse[list[ApprovalResponse]]:
    """Every approval step for one change, ordered by level."""
    rows = await approvals.list_for_change(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ApprovalResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} approval step(s).",
    )


@router.post(
    "/approvals/{approval_id}/decide",
    response_model=SuccessResponse[ApprovalResponse],
    summary="Record one approver's decision",
)
async def decide_approval(
    organization_id: UUID,
    approval_id: UUID,
    body: ApprovalDecideRequest,
    approvals: ApprovalSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ApprovalResponse]:
    """Approve, reject, or conditionally approve one step."""
    updated = await approvals.decide(
        organization_id, approval_id, decision=body.decision, comment=body.comment
    )
    await audit.record(
        organization_id,
        action=AuditAction.APPROVAL_DECIDED,
        entity_type="approval",
        entity_id=approval_id,
        actor_id=str(caller),
        summary=f"Approval step decided: {body.decision!s}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ApprovalResponse.model_validate(updated), message="Decision recorded."
    )


@router.post(
    "/approvals/{approval_id}/delegate",
    response_model=SuccessResponse[ApprovalResponse],
    summary="Delegate a pending approval step",
)
async def delegate_approval(
    organization_id: UUID,
    approval_id: UUID,
    body: ApprovalDelegateRequest,
    approvals: ApprovalSvc,
) -> SuccessResponse[ApprovalResponse]:
    """Reassign a pending step to someone else."""
    created = await approvals.delegate(organization_id, approval_id, delegated_to=body.delegated_to)
    return SuccessResponse(
        meta=_meta(), data=ApprovalResponse.model_validate(created), message="Approval delegated."
    )


__all__ = ["router"]
