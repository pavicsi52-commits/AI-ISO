"""Finding, exception, risk, and remediation endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    ExceptionSvc,
    FindingSvc,
    RemediationSvc,
    RiskSvc,
)
from app.models.enums import (
    AuditAction,
    ExceptionStatus,
    FindingSeverity,
    FindingStatus,
    RemediationStatus,
    RiskStatus,
)
from app.schemas.compliance import (
    ExceptionCreateRequest,
    ExceptionDecisionRequest,
    ExceptionResponse,
    ExceptionReviewRequest,
    ExceptionRevokeRequest,
    FindingAssignRequest,
    FindingResponse,
    FindingUpdateRequest,
    RemediationCreateRequest,
    RemediationResponse,
    RemediationTransitionRequest,
    RemediationVerifyRequest,
    RiskAssessRequest,
    RiskCreateRequest,
    RiskResponse,
    RiskTransitionRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/compliance", tags=["governance"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id.

    The id is what ties a response a caller is holding to the log lines
    the request produced -- without it, "my assessment returned the
    wrong number" is unanswerable.
    """
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- findings ----------------------------------------------------------


@router.get(
    "/findings",
    response_model=SuccessResponse[list[FindingResponse]],
    summary="List findings",
)
async def list_findings(
    organization_id: UUID,
    findings: FindingSvc,
    status_filter: Annotated[FindingStatus | None, Query(alias="status")] = None,
    severity: FindingSeverity | None = None,
    control_id: UUID | None = None,
    framework_id: UUID | None = None,
    assignee_id: Annotated[str | None, Query(max_length=255)] = None,
    target_id: Annotated[str | None, Query(max_length=255)] = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[FindingResponse]]:
    """Findings, worst and oldest first.

    Not newest first: a queue sorted by "newest" buries the thing that
    has been broken longest, which is usually the thing that matters.
    """
    rows = await findings.list_findings(
        organization_id,
        status=status_filter,
        severity=severity,
        control_id=control_id,
        framework_id=framework_id,
        assignee_id=assignee_id,
        target_id=target_id,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[FindingResponse.model_validate(one) for one in rows],
        message="Findings listed.",
    )


@router.get(
    "/findings/summary",
    response_model=SuccessResponse[dict[str, Any]],
    summary="How the finding queue stands",
)
async def finding_summary(
    organization_id: UUID, findings: FindingSvc
) -> SuccessResponse[dict[str, Any]]:
    """Open counts by severity, and how many are overdue."""
    return SuccessResponse(
        meta=_meta(),
        data=await findings.summary(organization_id),
        message="Finding summary computed.",
    )


@router.get(
    "/findings/overdue",
    response_model=SuccessResponse[list[FindingResponse]],
    summary="List overdue findings",
)
async def overdue_findings(
    organization_id: UUID,
    findings: FindingSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[FindingResponse]]:
    """Open findings past their due date."""
    rows = await findings.overdue(organization_id, limit=limit)
    return SuccessResponse(
        meta=_meta(),
        data=[FindingResponse.model_validate(one) for one in rows],
        message="Overdue findings listed.",
    )


@router.get(
    "/findings/{finding_id}",
    response_model=SuccessResponse[FindingResponse],
    summary="Read one finding",
)
async def get_finding(
    organization_id: UUID, finding_id: UUID, findings: FindingSvc
) -> SuccessResponse[FindingResponse]:
    """One finding."""
    found = await findings.get(organization_id, finding_id)
    return SuccessResponse(
        meta=_meta(), data=FindingResponse.model_validate(found), message="Finding read."
    )


@router.post(
    "/findings/{finding_id}/assign",
    response_model=SuccessResponse[FindingResponse],
    summary="Assign a finding",
)
async def assign_finding(
    organization_id: UUID,
    finding_id: UUID,
    body: FindingAssignRequest,
    findings: FindingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FindingResponse]:
    """Give a finding an owner."""
    updated = await findings.assign(
        organization_id, finding_id, assignee_id=body.assignee_id, actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.FINDING_UPDATED,
        entity_type="finding",
        entity_id=finding_id,
        actor_id=str(caller),
        summary=f"Assigned finding to {body.assignee_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=FindingResponse.model_validate(updated), message="Finding assigned."
    )


@router.post(
    "/findings/{finding_id}/transition",
    response_model=SuccessResponse[FindingResponse],
    summary="Move a finding through its lifecycle",
)
async def transition_finding(
    organization_id: UUID,
    finding_id: UUID,
    body: FindingUpdateRequest,
    findings: FindingSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FindingResponse]:
    """Change a finding's status.

    ``verified`` is refused here with a 409. That status means a
    re-assessment confirmed the control passes, which only the
    remediation verification path can establish -- letting it be set by
    hand would make the one status that means *proven* mean *asserted*.
    """
    updated = await findings.transition(
        organization_id, finding_id, target=body.status, note=body.note, actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.FINDING_UPDATED,
        entity_type="finding",
        entity_id=finding_id,
        actor_id=str(caller),
        summary=f"Moved finding to {str(body.status)!r}.",
        changes={"status": str(body.status), "note": body.note},
    )
    return SuccessResponse(
        meta=_meta(), data=FindingResponse.model_validate(updated), message="Finding updated."
    )


# ---- exceptions ---------------------------------------------------------


@router.get(
    "/exceptions",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="List compliance exceptions",
)
async def list_exceptions(
    organization_id: UUID,
    exceptions: ExceptionSvc,
    status_filter: Annotated[ExceptionStatus | None, Query(alias="status")] = None,
    control_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ExceptionResponse]]:
    """Exceptions, newest first."""
    rows = await exceptions.list_exceptions(
        organization_id,
        status=status_filter,
        control_id=control_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[ExceptionResponse.model_validate(one) for one in rows],
        message="Exceptions listed.",
    )


@router.post(
    "/exceptions",
    response_model=SuccessResponse[ExceptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Request a compliance exception",
)
async def request_exception(
    organization_id: UUID,
    body: ExceptionCreateRequest,
    exceptions: ExceptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """Ask for a control to be waived.

    Created ``REQUESTED``, never active. An exception that took effect
    the moment somebody asked for one would make the approval step
    decorative.
    """
    created = await exceptions.request(
        organization_id,
        control_id=body.control_id,
        title=body.title,
        business_justification=body.business_justification,
        kind=body.kind,
        expires_at=body.expires_at,
        risk_acceptance=body.risk_acceptance,
        compensating_control=body.compensating_control,
        target_type=body.target_type,
        target_id=body.target_id,
        review_interval_days=body.review_interval_days,
        requested_by=body.requested_by or str(caller),
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.EXCEPTION_REQUESTED,
        entity_type="exception",
        entity_id=created.id,
        entity_reference=created.title,
        actor_id=str(caller),
        summary=f"Requested exception {created.title!r}.",
        changes={"justification": body.business_justification},
    )
    return SuccessResponse(
        meta=_meta(), data=ExceptionResponse.model_validate(created), message="Exception requested."
    )


@router.get(
    "/exceptions/expiring",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="List exceptions about to lapse",
)
async def expiring_exceptions(
    organization_id: UUID,
    exceptions: ExceptionSvc,
    notify_user_id: Annotated[str | None, Query(max_length=255)] = None,
) -> SuccessResponse[list[ExceptionResponse]]:
    """Waivers about to lapse, optionally warning somebody."""
    rows = await exceptions.warn_expiring(organization_id, notify_user_id=notify_user_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ExceptionResponse.model_validate(one) for one in rows],
        message="Expiring exceptions listed.",
    )


@router.get(
    "/exceptions/overused",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="List exceptions that have become the real policy",
)
async def overused_exceptions(
    organization_id: UUID,
    exceptions: ExceptionSvc,
    threshold: Annotated[int, Query(ge=1, le=100_000)] = 100,
) -> SuccessResponse[list[ExceptionResponse]]:
    """Waivers relied on so often they are no longer exceptions."""
    rows = await exceptions.overused(organization_id, threshold=threshold)
    return SuccessResponse(
        meta=_meta(),
        data=[ExceptionResponse.model_validate(one) for one in rows],
        message="Overused exceptions listed.",
    )


@router.get(
    "/exceptions/due-for-review",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="List exceptions whose review is overdue",
)
async def exceptions_due_for_review(
    organization_id: UUID, exceptions: ExceptionSvc
) -> SuccessResponse[list[ExceptionResponse]]:
    """Live waivers whose review date has passed, permanent ones included."""
    rows = await exceptions.due_for_review(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ExceptionResponse.model_validate(one) for one in rows],
        message="Exceptions due for review listed.",
    )


@router.get(
    "/exceptions/{exception_id}",
    response_model=SuccessResponse[ExceptionResponse],
    summary="Read one exception",
)
async def get_exception(
    organization_id: UUID, exception_id: UUID, exceptions: ExceptionSvc
) -> SuccessResponse[ExceptionResponse]:
    """One exception."""
    found = await exceptions.get(organization_id, exception_id)
    return SuccessResponse(
        meta=_meta(), data=ExceptionResponse.model_validate(found), message="Exception read."
    )


@router.post(
    "/exceptions/{exception_id}/decide",
    response_model=SuccessResponse[ExceptionResponse],
    summary="Approve or refuse a requested exception",
)
async def decide_exception(
    organization_id: UUID,
    exception_id: UUID,
    body: ExceptionDecisionRequest,
    exceptions: ExceptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """Grant or refuse a waiver."""
    decided = (
        await exceptions.approve(
            organization_id, exception_id, approved_by=body.decided_by, actor_id=caller
        )
        if body.approve
        else await exceptions.reject(
            organization_id,
            exception_id,
            reason=body.reason or "No reason recorded.",
            actor_id=caller,
        )
    )
    await audit.record(
        organization_id,
        action=AuditAction.EXCEPTION_APPROVED,
        entity_type="exception",
        entity_id=exception_id,
        entity_reference=decided.title,
        actor_id=str(caller),
        succeeded=body.approve,
        summary=(f"{'Approved' if body.approve else 'Rejected'} exception {decided.title!r}."),
        changes={"decided_by": body.decided_by, "reason": body.reason},
    )
    return SuccessResponse(
        meta=_meta(), data=ExceptionResponse.model_validate(decided), message="Exception decided."
    )


@router.post(
    "/exceptions/{exception_id}/review",
    response_model=SuccessResponse[ExceptionResponse],
    summary="Record a periodic review of an exception",
)
async def review_exception(
    organization_id: UUID,
    exception_id: UUID,
    body: ExceptionReviewRequest,
    exceptions: ExceptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """Record a review. Concluding "no longer needed" revokes the waiver."""
    reviewed = await exceptions.review(
        organization_id,
        exception_id,
        reviewed_by=body.reviewed_by,
        still_needed=body.still_needed,
        note=body.note,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.EXCEPTION_APPROVED,
        entity_type="exception",
        entity_id=exception_id,
        entity_reference=reviewed.title,
        actor_id=str(caller),
        summary=(
            f"Reviewed exception {reviewed.title!r}; "
            f"{'still needed' if body.still_needed else 'revoked as no longer needed'}."
        ),
    )
    return SuccessResponse(
        meta=_meta(), data=ExceptionResponse.model_validate(reviewed), message="Exception reviewed."
    )


@router.delete(
    "/exceptions/{exception_id}",
    response_model=SuccessResponse[ExceptionResponse],
    summary="Revoke a live exception",
)
async def revoke_exception(
    organization_id: UUID,
    exception_id: UUID,
    body: ExceptionRevokeRequest,
    exceptions: ExceptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """End a waiver early."""
    revoked = await exceptions.revoke(
        organization_id, exception_id, reason=body.reason, actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.EXCEPTION_REVOKED,
        entity_type="exception",
        entity_id=exception_id,
        entity_reference=revoked.title,
        actor_id=str(caller),
        summary=f"Revoked exception {revoked.title!r}: {body.reason}",
    )
    return SuccessResponse(
        meta=_meta(), data=ExceptionResponse.model_validate(revoked), message="Exception revoked."
    )


# ---- risk register --------------------------------------------------------


@router.get(
    "/risk-register",
    response_model=SuccessResponse[list[RiskResponse]],
    summary="List the risk register",
)
async def list_risks(
    organization_id: UUID,
    risks: RiskSvc,
    status_filter: Annotated[RiskStatus | None, Query(alias="status")] = None,
    owner_id: Annotated[str | None, Query(max_length=255)] = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[RiskResponse]]:
    """Risks, worst first."""
    rows = await risks.list_risks(
        organization_id,
        status=status_filter,
        owner_id=owner_id,
        open_only=open_only,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[RiskResponse.model_validate(one) for one in rows],
        message="Risk register listed.",
    )


@router.post(
    "/risk-register",
    response_model=SuccessResponse[RiskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a risk",
)
async def register_risk(
    organization_id: UUID,
    body: RiskCreateRequest,
    risks: RiskSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RiskResponse]:
    """Add a risk.

    Severity is derived from likelihood and impact and cannot be supplied
    -- a register that accepts one lets the person who owns a risk grade
    their own risk.
    """
    created = await risks.register(
        organization_id,
        title=body.title,
        likelihood=body.likelihood,
        impact=body.impact,
        category=body.category,
        description=body.description,
        owner_id=body.owner_id,
        owner_team=body.owner_team,
        mitigation_plan=body.mitigation_plan,
        control_ids=body.control_ids,
        finding_ids=body.finding_ids,
        review_interval_days=body.review_interval_days,
        notify_user_id=body.notify_user_id,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.RISK_REGISTERED,
        entity_type="risk",
        entity_id=created.id,
        entity_reference=created.reference,
        actor_id=str(caller),
        summary=f"Registered risk {created.reference} at {str(created.severity)!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=RiskResponse.model_validate(created), message="Risk registered."
    )


@router.get(
    "/risk-register/due-for-review",
    response_model=SuccessResponse[list[RiskResponse]],
    summary="List risks whose review is overdue",
)
async def risks_due_for_review(
    organization_id: UUID, risks: RiskSvc
) -> SuccessResponse[list[RiskResponse]]:
    """Open risks whose review date has passed."""
    rows = await risks.due_for_review(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[RiskResponse.model_validate(one) for one in rows],
        message="Risks due for review listed.",
    )


@router.get(
    "/risk-register/{risk_id}",
    response_model=SuccessResponse[RiskResponse],
    summary="Read one risk",
)
async def get_risk(
    organization_id: UUID, risk_id: UUID, risks: RiskSvc
) -> SuccessResponse[RiskResponse]:
    """One risk."""
    found = await risks.get(organization_id, risk_id)
    return SuccessResponse(
        meta=_meta(), data=RiskResponse.model_validate(found), message="Risk read."
    )


@router.put(
    "/risk-register/{risk_id}/assessment",
    response_model=SuccessResponse[RiskResponse],
    summary="Re-score a risk",
)
async def assess_risk(
    organization_id: UUID,
    risk_id: UUID,
    body: RiskAssessRequest,
    risks: RiskSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RiskResponse]:
    """Re-score a risk, inherent or residual."""
    updated = await risks.update_assessment(
        organization_id,
        risk_id,
        likelihood=body.likelihood,
        impact=body.impact,
        residual_likelihood=body.residual_likelihood,
        residual_impact=body.residual_impact,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.RISK_UPDATED,
        entity_type="risk",
        entity_id=risk_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Re-scored risk {updated.reference} to {str(updated.severity)!r}.",
        changes=body.model_dump(exclude_none=True),
    )
    return SuccessResponse(
        meta=_meta(), data=RiskResponse.model_validate(updated), message="Risk re-scored."
    )


@router.post(
    "/risk-register/{risk_id}/transition",
    response_model=SuccessResponse[RiskResponse],
    summary="Move a risk through its lifecycle",
)
async def transition_risk(
    organization_id: UUID,
    risk_id: UUID,
    body: RiskTransitionRequest,
    risks: RiskSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RiskResponse]:
    """Change a risk's status. Closing needs a reason."""
    updated = await risks.transition(
        organization_id, risk_id, target=body.status, reason=body.reason, actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.RISK_UPDATED,
        entity_type="risk",
        entity_id=risk_id,
        entity_reference=updated.reference,
        actor_id=str(caller),
        summary=f"Moved risk {updated.reference} to {str(body.status)!r}.",
        changes={"status": str(body.status), "reason": body.reason},
    )
    return SuccessResponse(
        meta=_meta(), data=RiskResponse.model_validate(updated), message="Risk updated."
    )


@router.post(
    "/risk-register/{risk_id}/review",
    response_model=SuccessResponse[RiskResponse],
    summary="Record a review of a risk",
)
async def review_risk(
    organization_id: UUID, risk_id: UUID, risks: RiskSvc, caller: CurrentUserId
) -> SuccessResponse[RiskResponse]:
    """Note that somebody looked at a risk, and reset its clock."""
    reviewed = await risks.record_review(organization_id, risk_id, actor_id=caller)
    return SuccessResponse(
        meta=_meta(), data=RiskResponse.model_validate(reviewed), message="Risk reviewed."
    )


# ---- remediation ----------------------------------------------------------


@router.get(
    "/remediation",
    response_model=SuccessResponse[list[RemediationResponse]],
    summary="List remediation tasks",
)
async def list_remediations(
    organization_id: UUID,
    remediation: RemediationSvc,
    status_filter: Annotated[RemediationStatus | None, Query(alias="status")] = None,
    assignee_id: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[RemediationResponse]]:
    """Remediation tasks, newest first."""
    rows = await remediation.list_tasks(
        organization_id,
        status=status_filter,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[RemediationResponse.model_validate(one) for one in rows],
        message="Remediation tasks listed.",
    )


@router.post(
    "/remediation",
    response_model=SuccessResponse[RemediationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Propose a remediation",
)
async def propose_remediation(
    organization_id: UUID,
    body: RemediationCreateRequest,
    remediation: RemediationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RemediationResponse]:
    """Propose a fix for a finding."""
    created = await remediation.propose(
        organization_id,
        finding_id=body.finding_id,
        title=body.title,
        kind=body.kind,
        description=body.description,
        recommended_action=body.recommended_action,
        playbook_id=body.playbook_id,
        workflow_id=body.workflow_id,
        automation_job_id=body.automation_job_id,
        assignee_id=body.assignee_id,
        due_at=body.due_at,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.REMEDIATION_CREATED,
        entity_type="remediation",
        entity_id=created.id,
        entity_reference=created.title,
        actor_id=str(caller),
        summary=f"Proposed remediation {created.title!r}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=RemediationResponse.model_validate(created),
        message="Remediation proposed.",
    )


@router.get(
    "/remediation/{task_id}",
    response_model=SuccessResponse[RemediationResponse],
    summary="Read one remediation task",
)
async def get_remediation(
    organization_id: UUID, task_id: UUID, remediation: RemediationSvc
) -> SuccessResponse[RemediationResponse]:
    """One remediation task."""
    found = await remediation.get(organization_id, task_id)
    return SuccessResponse(
        meta=_meta(), data=RemediationResponse.model_validate(found), message="Remediation read."
    )


@router.post(
    "/remediation/{task_id}/transition",
    response_model=SuccessResponse[RemediationResponse],
    summary="Move a remediation through its lifecycle",
)
async def transition_remediation(
    organization_id: UUID,
    task_id: UUID,
    body: RemediationTransitionRequest,
    remediation: RemediationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RemediationResponse]:
    """Change a remediation's status.

    ``verified`` is refused here with a 409: it means a re-assessment
    confirmed the control passes, which only ``/verify`` can establish.
    """
    updated = await remediation.transition(
        organization_id, task_id, target=body.status, note=body.note, actor_id=caller
    )
    return SuccessResponse(
        meta=_meta(),
        data=RemediationResponse.model_validate(updated),
        message="Remediation updated.",
    )


@router.post(
    "/remediation/{task_id}/verify",
    response_model=SuccessResponse[RemediationResponse],
    summary="Verify that a remediation actually worked",
)
async def verify_remediation(
    organization_id: UUID,
    task_id: UUID,
    body: RemediationVerifyRequest,
    remediation: RemediationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RemediationResponse]:
    """Read a fresh result and close the finding only if the control passes.

    Answers 200 whether or not verification succeeded -- "we checked, and
    it still fails" is a successful answer to the question asked, and the
    body says which happened.
    """
    verified, passed = await remediation.verify(
        organization_id,
        task_id,
        verified_by=body.verified_by,
        notify_user_id=body.notify_user_id,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.REMEDIATION_VERIFIED,
        entity_type="remediation",
        entity_id=task_id,
        entity_reference=verified.title,
        actor_id=str(caller),
        succeeded=passed,
        summary=(
            f"Verified remediation {verified.title!r}: the control now passes."
            if passed
            else (f"Could not verify remediation {verified.title!r}: {verified.verification_note}")
        ),
    )
    return SuccessResponse(
        meta=_meta(),
        data=RemediationResponse.model_validate(verified),
        message=(
            "Remediation verified; the finding is closed."
            if passed
            else (
                "Remediation not verified. The control does not yet pass, so the "
                "finding stays open."
            )
        ),
    )


@router.get(
    "/findings/{finding_id}/remediation",
    response_model=SuccessResponse[list[RemediationResponse]],
    summary="List remediation attempts for a finding",
)
async def remediation_for_finding(
    organization_id: UUID, finding_id: UUID, remediation: RemediationSvc
) -> SuccessResponse[list[RemediationResponse]]:
    """Every attempt to fix one finding."""
    rows = await remediation.for_finding(organization_id, finding_id)
    return SuccessResponse(
        meta=_meta(),
        data=[RemediationResponse.model_validate(one) for one in rows],
        message="Remediation attempts listed.",
    )
