"""Decisions, violations, exceptions, approvals, quotas, statistics, reports, audit.

The operational surface: what an administrator reads and manages, as
opposed to ``/policies/evaluate``, which every service calls.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    ApprovalSvc,
    AttributeRepo,
    AuditSvc,
    ComplianceSvc,
    CurrentUserId,
    DecisionSvc,
    QuotaSvc,
    ReportSvc,
    StatisticsSvc,
)
from app.models.enums import (
    ApprovalStatus,
    AuditAction,
    PolicyEffect,
    QuotaScope,
    ReportKind,
    ViolationStatus,
)
from app.schemas.policy import (
    ApprovalDecisionRequest,
    ApprovalResponse,
    AuditEntryResponse,
    ExceptionCreateRequest,
    ExceptionResponse,
    QuotaCreateRequest,
    QuotaResponse,
    QuotaUpdateRequest,
    ReportCreateRequest,
    ReportResponse,
    StatisticsResponse,
    StoredDecisionResponse,
    ViolationResolveRequest,
    ViolationResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/policies", tags=["Operations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- decisions --------------------------------------------------------


@router.get(
    "/decisions",
    response_model=SuccessResponse[list[StoredDecisionResponse]],
    summary="Recorded decisions",
)
async def list_decisions(
    organization_id: UUID,
    decisions: DecisionSvc,
    caller: CurrentUserId,
    effect: PolicyEffect | None = None,
    subject_id: str | None = None,
    denied_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[StoredDecisionResponse]]:
    """Decisions, most recent first.

    Simulated decisions are excluded. A simulation runs the real engine,
    so its rows are otherwise indistinguishable from live ones, and a
    what-if analysis silently inflating the denial rate would break the
    metric exactly when somebody is using it to plan a change.
    """
    del caller
    rows = await decisions.history(
        organization_id,
        effect=effect,
        subject_id=subject_id,
        denied_only=denied_only,
        limit=limit,
    )
    return SuccessResponse(
        message=f"Found {len(rows)} decisions.",
        data=[StoredDecisionResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.get(
    "/decisions/by-request/{request_id}",
    response_model=SuccessResponse[StoredDecisionResponse],
    summary="Find the decision behind a correlation id",
)
async def decision_by_request(
    request_id: str,
    organization_id: UUID,
    decisions: DecisionSvc,
    caller: CurrentUserId,
) -> SuccessResponse[StoredDecisionResponse]:
    """The decision that produced one caller's refusal.

    How "I got a 403 and I do not know why" is answered across service
    boundaries -- the caller quotes their request id and gets the trace.

    Raises:
        NotFoundError: If nothing was recorded under that id.
    """
    del caller
    found = await decisions.by_request_id(organization_id, request_id)
    if found is None:
        raise NotFoundError(f"No decision recorded for request id {request_id!r}.")
    return SuccessResponse(
        message="Decision retrieved.",
        data=StoredDecisionResponse.model_validate(found),
        meta=_meta(),
    )


# ---- violations -------------------------------------------------------


@router.get(
    "/violations",
    response_model=SuccessResponse[list[ViolationResponse]],
    summary="Recorded violations",
)
async def list_violations(
    organization_id: UUID,
    compliance: ComplianceSvc,
    caller: CurrentUserId,
    violation_status: ViolationStatus | None = None,
    severity: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[ViolationResponse]]:
    """Violations, most recent first."""
    del caller
    rows = await compliance.list_violations(
        organization_id, status=violation_status, severity=severity, limit=limit
    )
    return SuccessResponse(
        message=f"Found {len(rows)} violations.",
        data=[ViolationResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "/violations/{violation_id}/acknowledge",
    response_model=SuccessResponse[ViolationResponse],
    summary="Acknowledge a violation",
)
async def acknowledge_violation(
    violation_id: UUID,
    organization_id: UUID,
    compliance: ComplianceSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ViolationResponse]:
    """Mark a violation as seen.

    A distinct state from resolved: "somebody knows about this" and "this
    is fixed" are different facts, and collapsing them makes an
    acknowledged-but-unfixed violation disappear from the list of things
    to do.
    """
    updated = await compliance.acknowledge(organization_id, violation_id, actor_id=caller)
    return SuccessResponse(
        message="Violation acknowledged.",
        data=ViolationResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/violations/{violation_id}/resolve",
    response_model=SuccessResponse[ViolationResponse],
    summary="Close a violation",
)
async def resolve_violation(
    violation_id: UUID,
    organization_id: UUID,
    body: ViolationResolveRequest,
    compliance: ComplianceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ViolationResponse]:
    """Close a violation, fixed or explicitly waived.

    The note is required. A violation closed without a stated reason is
    indistinguishable from one somebody clicked past.
    """
    updated = await compliance.resolve(
        organization_id,
        violation_id,
        note=body.note,
        waived=body.waived,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.VIOLATION_RECORDED,
        entity_type="violation",
        entity_id=str(violation_id),
        actor_id=caller,
        reason=body.note,
        context={"waived": body.waived},
    )
    return SuccessResponse(
        message="Violation waived." if body.waived else "Violation resolved.",
        data=ViolationResponse.model_validate(updated),
        meta=_meta(),
    )


# ---- exceptions -------------------------------------------------------


@router.get(
    "/exceptions",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="Policy exceptions",
)
async def list_exceptions(
    organization_id: UUID,
    compliance: ComplianceSvc,
    caller: CurrentUserId,
    active_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[ExceptionResponse]]:
    """Waivers, newest first."""
    del caller
    rows = await compliance.list_exceptions(organization_id, active_only=active_only, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} exceptions.",
        data=[ExceptionResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "/exceptions",
    response_model=SuccessResponse[ExceptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Grant a policy exception",
)
async def grant_exception(
    organization_id: UUID,
    body: ExceptionCreateRequest,
    compliance: ComplianceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """Waive one policy, for a bounded time and scope.

    Both the reason and the expiry are required, and the expiry is capped
    by the service. A permanent exception is not an exception -- it is an
    undocumented policy change that no review will surface, because it
    does not look like one.
    """
    granted = await compliance.grant_exception(
        organization_id,
        policy_id=body.policy_id,
        reason=body.reason,
        expires_at=body.expires_at,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="exception",
        entity_id=str(granted.id),
        actor_id=caller,
        reason=body.reason,
        after={
            "policy_id": str(body.policy_id),
            "expires_at": granted.expires_at.isoformat(),
        },
    )
    return SuccessResponse(
        message=(f"Exception granted until {granted.expires_at.isoformat()}."),
        data=ExceptionResponse.model_validate(granted),
        meta=_meta(),
    )


@router.delete(
    "/exceptions/{exception_id}",
    response_model=SuccessResponse[ExceptionResponse],
    summary="Revoke a policy exception",
)
async def revoke_exception(
    exception_id: UUID,
    organization_id: UUID,
    compliance: ComplianceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExceptionResponse]:
    """End a waiver early."""
    revoked = await compliance.revoke_exception(organization_id, exception_id, actor_id=caller)
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="exception",
        entity_id=str(exception_id),
        actor_id=caller,
        context={"revoked": True},
    )
    return SuccessResponse(
        message="Exception revoked; the policy applies again.",
        data=ExceptionResponse.model_validate(revoked),
        meta=_meta(),
    )


@router.get(
    "/exceptions/overused",
    response_model=SuccessResponse[list[ExceptionResponse]],
    summary="Exceptions that have become the real policy",
)
async def overused_exceptions(
    organization_id: UUID,
    compliance: ComplianceSvc,
    caller: CurrentUserId,
    threshold: Annotated[int, Query(ge=1, le=100_000)] = 100,
) -> SuccessResponse[list[ExceptionResponse]]:
    """Waivers relied on often enough to be worth revisiting.

    The number that makes a quiet problem visible: a waiver used a
    thousand times is not an exception, and nothing else in the system
    would ever say so.
    """
    del caller
    rows = await compliance.overused_exceptions(organization_id, threshold=threshold)
    return SuccessResponse(
        message=f"{len(rows)} exception(s) used at least {threshold} times.",
        data=[ExceptionResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


# ---- approvals --------------------------------------------------------


@router.get(
    "/approvals",
    response_model=SuccessResponse[list[ApprovalResponse]],
    summary="Approval obligations",
)
async def list_approvals(
    organization_id: UUID,
    approvals: ApprovalSvc,
    caller: CurrentUserId,
    approval_status: ApprovalStatus | None = None,
    subject_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[ApprovalResponse]]:
    """Approvals, most recently requested first."""
    del caller
    rows = await approvals.list_approvals(
        organization_id, status=approval_status, subject_id=subject_id, limit=limit
    )
    return SuccessResponse(
        message=f"Found {len(rows)} approvals.",
        data=[ApprovalResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "/approvals/{approval_id}/decide",
    response_model=SuccessResponse[ApprovalResponse],
    summary="Record an approval decision",
)
async def decide_approval(
    approval_id: UUID,
    organization_id: UUID,
    body: ApprovalDecisionRequest,
    approvals: ApprovalSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ApprovalResponse]:
    """Record one approver's answer.

    One rejection ends it, whatever the level count: waiting for a third
    opinion after somebody has objected turns a veto into a vote.
    """
    updated = await approvals.record_decision(
        organization_id,
        approval_id,
        approver_id=body.approver_id,
        approved=body.approved,
        comment=body.comment,
        approver_roles=body.approver_roles,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.APPROVAL_CHANGED,
        entity_type="approval",
        entity_id=str(approval_id),
        actor_id=caller,
        reason=body.comment or None,
        after={"approved": body.approved, "status": str(updated.status)},
    )
    return SuccessResponse(
        message=f"Approval is now {updated.status!s}.",
        data=ApprovalResponse.model_validate(updated),
        meta=_meta(),
    )


@router.get(
    "/approvals/{approval_id}",
    response_model=SuccessResponse[dict[str, object]],
    summary="One approval and its derived state",
)
async def get_approval(
    approval_id: UUID,
    organization_id: UUID,
    approvals: ApprovalSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, object]]:
    """One approval, with its state re-derived from the recorded answers.

    Derived rather than read off the status column, so a row whose
    deadline passed since it was last written reports as expired without
    waiting for the sweep.
    """
    del caller
    stored = await approvals.get(organization_id, approval_id)
    state = await approvals.state_of(organization_id, approval_id)
    return SuccessResponse(
        message=f"Approval is {state.status!s}.",
        data={
            "approval": ApprovalResponse.model_validate(stored).model_dump(mode="json"),
            "state": state.as_dict(),
        },
        meta=_meta(),
    )


# ---- quotas -----------------------------------------------------------


@router.get(
    "/quotas",
    response_model=SuccessResponse[list[QuotaResponse]],
    summary="Consumption budgets",
)
async def list_quotas(
    organization_id: UUID,
    quotas: QuotaSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[QuotaResponse]]:
    """Every budget an organization has defined."""
    del caller
    rows = await quotas.list_quotas(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} quotas.",
        data=[QuotaResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "/quotas",
    response_model=SuccessResponse[QuotaResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Define a consumption budget",
)
async def create_quota(
    organization_id: UUID,
    body: QuotaCreateRequest,
    quotas: QuotaSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[QuotaResponse]:
    """Create a budget.

    A limit of zero means *unlimited*. Deliberate: a quota created
    without a limit would otherwise refuse every request for that
    resource, and an accidental total outage is far worse than an
    accidental absence of enforcement.
    """
    created = await quotas.define(
        organization_id,
        scope=body.scope,
        scope_id=body.scope_id,
        resource=body.resource,
        limit_value=body.limit_value,
        period=body.period,
        is_hard_limit=body.is_hard_limit,
        description=body.description,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="quota",
        entity_id=f"{body.scope}:{body.scope_id}:{body.resource}",
        actor_id=caller,
        after={"limit": body.limit_value, "period": str(body.period)},
    )
    return SuccessResponse(
        message=(
            f"Quota for {body.resource!r} defined"
            + (" (unlimited)." if body.limit_value <= 0 else f" at {body.limit_value:g}.")
        ),
        data=QuotaResponse.model_validate(created),
        meta=_meta(),
    )


@router.put(
    "/quotas",
    response_model=SuccessResponse[QuotaResponse],
    summary="Change a budget's ceiling",
)
async def update_quota(
    organization_id: UUID,
    body: QuotaUpdateRequest,
    quotas: QuotaSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    scope: QuotaScope = QuotaScope.ORGANIZATION,
    scope_id: str = "",
    resource: str = "requests",
) -> SuccessResponse[QuotaResponse]:
    """Raise or lower a limit.

    Consumption is deliberately untouched: raising a limit should let
    already-blocked work through, but forgiving what has already been
    used is a different decision nobody made.
    """
    updated = await quotas.update_limit(
        organization_id,
        scope=scope,
        scope_id=scope_id,
        resource=resource,
        limit_value=body.limit_value,
        is_hard_limit=body.is_hard_limit,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="quota",
        entity_id=f"{scope}:{scope_id}:{resource}",
        actor_id=caller,
        after={"limit": updated.limit_value, "hard": updated.is_hard_limit},
    )
    return SuccessResponse(
        message="Quota updated.",
        data=QuotaResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/quotas/reset",
    response_model=SuccessResponse[QuotaResponse],
    summary="Zero a budget's consumption",
)
async def reset_quota(
    organization_id: UUID,
    quotas: QuotaSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    scope: QuotaScope = QuotaScope.ORGANIZATION,
    scope_id: str = "",
    resource: str = "requests",
) -> SuccessResponse[QuotaResponse]:
    """Start a fresh period for one budget."""
    reset = await quotas.reset(organization_id, scope=scope, scope_id=scope_id, resource=resource)
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="quota",
        entity_id=f"{scope}:{scope_id}:{resource}",
        actor_id=caller,
        context={"reset": True},
    )
    return SuccessResponse(
        message="Quota reset.",
        data=QuotaResponse.model_validate(reset),
        meta=_meta(),
    )


# ---- statistics and reports ------------------------------------------


@router.get(
    "/statistics",
    response_model=SuccessResponse[StatisticsResponse],
    summary="Policy analytics",
)
async def get_statistics(
    organization_id: UUID,
    statistics: StatisticsSvc,
    caller: CurrentUserId,
    recompute: bool = False,
) -> SuccessResponse[StatisticsResponse]:
    """The organization's rollup.

    Every figure is derived from rows somebody can go and count, never
    incremented -- a counter bumped per decision drifts the moment one
    write is lost, and nothing can tell you it has.
    """
    del caller
    record = (
        await statistics.refresh(organization_id)
        if recompute
        else await statistics.get(organization_id)
    )
    if record is None:
        record = await statistics.refresh(organization_id)
    return SuccessResponse(
        message="Statistics retrieved.",
        data=StatisticsResponse.model_validate(record),
        meta=_meta(),
    )


@router.get(
    "/reports",
    response_model=SuccessResponse[list[ReportResponse]],
    summary="Generated reports",
)
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    caller: CurrentUserId,
    kind: ReportKind | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[ReportResponse]]:
    """Reports, most recent first."""
    del caller
    rows = await reports.list_reports(organization_id, kind=kind, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} reports.",
        data=[ReportResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "/reports",
    response_model=SuccessResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
)
async def create_report(
    organization_id: UUID,
    body: ReportCreateRequest,
    reports: ReportSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ReportResponse]:
    """Build and store one report."""
    generated = await reports.generate(
        organization_id,
        kind=body.kind,
        title=body.title,
        parameters=body.parameters,
        actor_id=caller,
    )
    return SuccessResponse(
        message=generated.summary or f"{body.kind!s} report generated.",
        data=ReportResponse.model_validate(generated),
        meta=_meta(),
    )


@router.get(
    "/reports/{report_id}/download",
    summary="Download a report",
)
async def download_report(
    report_id: UUID,
    organization_id: UUID,
    reports: ReportSvc,
    caller: CurrentUserId,
) -> Response:
    """Return the rendered bytes, verified against their digest.

    Takes ``organization_id`` like every other route here. A report
    payload can hold every decision an organization has made, so the
    ownership check is the difference between a download and a
    disclosure.

    Raises:
        NotFoundError: If no such report exists in this organization.
        ValidationError: If it holds no payload or fails verification.
    """
    del caller
    found = await reports.get(organization_id, report_id)
    verification = reports.verify(found)
    if not verification["valid"] or found.payload is None:
        raise ValidationError(
            f"Report {report_id} cannot be served: "
            f"{verification.get('reason', 'checksum mismatch')}."
        )
    return Response(
        content=found.payload,
        media_type=found.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{found.kind}-report.json"',
            "X-Checksum-SHA256": found.checksum_sha256 or "",
        },
    )


# ---- audit and attributes --------------------------------------------


@router.get(
    "/audit",
    response_model=SuccessResponse[list[AuditEntryResponse]],
    summary="Policy audit trail",
)
async def audit_trail(
    organization_id: UUID,
    audit: AuditSvc,
    caller: CurrentUserId,
    action: AuditAction | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[AuditEntryResponse]]:
    """Audited actions, most recent first.

    ``DENIED`` outcomes are included -- a refused request is exactly what
    this trail exists to show.
    """
    del caller
    rows = await audit.list_for_org(organization_id, action=action, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} audit entries.",
        data=[AuditEntryResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.get(
    "/audit/summary",
    response_model=SuccessResponse[dict[str, object]],
    summary="Audit counts by action and outcome",
)
async def audit_summary(
    organization_id: UUID,
    audit: AuditSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 1_000,
) -> SuccessResponse[dict[str, object]]:
    """Audit counts grouped by action and by outcome."""
    del caller
    return SuccessResponse(
        message="Audit summarised.",
        data=await audit.summarise(organization_id, limit=limit),
        meta=_meta(),
    )


@router.get(
    "/attributes",
    response_model=SuccessResponse[list[dict[str, object]]],
    summary="The attribute catalogue",
)
async def list_attributes(
    organization_id: UUID,
    attributes: AttributeRepo,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 500,
) -> SuccessResponse[list[dict[str, object]]]:
    """Every attribute the estate knows how to supply.

    What a policy editor offers instead of a free-text box -- and what
    catches a policy referencing an attribute nothing will ever populate,
    which otherwise evaluates as missing forever and silently never
    matches.
    """
    del caller
    rows = await attributes.list_for_org(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} declared attributes.",
        data=[
            {
                "source": str(one.source),
                "path": one.path,
                "name": one.name,
                "description": one.description,
                "data_type": one.data_type,
                "allowed_values": one.allowed_values,
                "is_required": one.is_required,
                "is_sensitive": one.is_sensitive,
                "provided_by": one.provided_by,
            }
            for one in rows
        ],
        meta=_meta(),
    )


__all__ = ["router"]
