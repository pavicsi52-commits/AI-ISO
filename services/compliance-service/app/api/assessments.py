"""Assessment, scan, evidence, and result endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.responses.success import SuccessResponse

from app.api.deps import (
    AssessmentSvc,
    AuditSvc,
    CatalogueSvc,
    CurrentUserId,
    EvidenceSvc,
    FindingSvc,
    ScanRepo,
    ScoringSvc,
)
from app.assessments.engine import ControlResult, Target
from app.models.assessment import ComplianceScan
from app.models.enums import (
    FAILING_STATUSES,
    AssessmentStatus,
    AuditAction,
    ControlSeverity,
    EvidenceKind,
    EvidenceSource,
    ResultStatus,
    ScanKind,
    ScanStatus,
    result_status_of,
)
from app.schemas.compliance import (
    AssessmentCreateRequest,
    AssessmentResponse,
    AssessmentRunRequest,
    EvidenceCreateRequest,
    EvidenceResponse,
    EvidenceSupersedeRequest,
    ResultResponse,
    ScanRequest,
    ScanResponse,
    TargetPayload,
)

router = APIRouter(prefix="/compliance", tags=["assessments"])


def _target(payload: TargetPayload) -> Target:
    return Target(
        target_id=payload.target_id,
        target_type=payload.target_type,
        name=payload.name,
        payload=payload.payload,
        evidence_id=payload.evidence_id,
    )


@router.get(
    "/assessments",
    response_model=SuccessResponse[list[AssessmentResponse]],
    summary="List assessments",
)
async def list_assessments(
    organization_id: UUID,
    assessments: AssessmentSvc,
    status_filter: Annotated[AssessmentStatus | None, Query(alias="status")] = None,
    framework_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[AssessmentResponse]]:
    """Assessments, newest first."""
    rows = await assessments.list_assessments(
        organization_id,
        status=status_filter,
        framework_id=framework_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        data=[AssessmentResponse.model_validate(one) for one in rows],
        message="Assessments listed.",
    )


@router.post(
    "/assessments",
    response_model=SuccessResponse[AssessmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Plan an assessment",
)
async def create_assessment(
    organization_id: UUID,
    body: AssessmentCreateRequest,
    assessments: AssessmentSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AssessmentResponse]:
    """Plan an assessment. Planning does not run it."""
    created = await assessments.create(
        organization_id,
        name=body.name,
        description=body.description,
        kind=body.kind,
        scope=body.scope,
        scope_id=body.scope_id,
        framework_id=body.framework_id,
        parameters=body.parameters,
        triggered_by=str(caller),
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.ASSESSMENT_CREATED,
        entity_type="assessment",
        entity_id=created.id,
        entity_reference=created.name,
        actor_id=str(caller),
        summary=f"Planned assessment {created.name!r}.",
    )
    return SuccessResponse(
        data=AssessmentResponse.model_validate(created), message="Assessment planned."
    )


@router.post(
    "/assessments/{assessment_id}/run",
    response_model=SuccessResponse[AssessmentResponse],
    summary="Run a planned assessment",
)
async def run_assessment(
    organization_id: UUID,
    assessment_id: UUID,
    body: AssessmentRunRequest,
    assessments: AssessmentSvc,
    findings: FindingSvc,
    scoring: ScoringSvc,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AssessmentResponse]:
    """Execute an assessment, raise findings, and score it.

    Findings and scoring happen here rather than in a follow-up call
    because a run whose findings were never raised is a run that appears
    to have found nothing -- and the caller has no way to tell the two
    apart.
    """
    finished = await assessments.run(
        organization_id,
        assessment_id,
        targets=[_target(one) for one in body.targets],
        actor_id=caller,
    )

    raised = 0
    if body.raise_findings:
        results = await assessments.results_for(organization_id, assessment_id, limit=10_000)
        codes: dict[str, str] = {}
        for row in results:
            if result_status_of(row.status) not in FAILING_STATUSES:
                continue
            control = await catalogue.get_control(organization_id, row.control_id)
            codes[str(row.control_id)] = control.code
            _created, is_new = await findings.raise_from_result(
                organization_id,
                ControlResult(
                    control_id=str(row.control_id),
                    framework_id=str(row.framework_id) if row.framework_id else None,
                    status=result_status_of(row.status),
                    reason=row.reason or "",
                    target_id=row.target_id,
                    target_type=row.target_type,
                    target_name=row.target_name,
                    severity=ControlSeverity(str(control.severity)),
                ),
                assessment_id=assessment_id,
                result_id=row.id,
                control_code=control.code,
                actor_id=caller,
            )
            raised += int(is_new)
        finished.findings_raised = raised

    await scoring.score_assessment(organization_id, assessment_id, actor_id=caller)

    await audit.record(
        organization_id,
        action=AuditAction.ASSESSMENT_COMPLETED,
        entity_type="assessment",
        entity_id=assessment_id,
        entity_reference=finished.name,
        actor_id=str(caller),
        summary=(
            f"Ran assessment {finished.name!r}: {finished.controls_passed} passed, "
            f"{finished.controls_failed} failed, {raised} new finding(s)."
        ),
    )
    return SuccessResponse(
        data=AssessmentResponse.model_validate(finished), message="Assessment complete."
    )


@router.get(
    "/assessments/{assessment_id}",
    response_model=SuccessResponse[AssessmentResponse],
    summary="Read one assessment",
)
async def get_assessment(
    organization_id: UUID, assessment_id: UUID, assessments: AssessmentSvc
) -> SuccessResponse[AssessmentResponse]:
    """One assessment."""
    found = await assessments.get(organization_id, assessment_id)
    return SuccessResponse(
        data=AssessmentResponse.model_validate(found), message="Assessment read."
    )


@router.get(
    "/assessments/{assessment_id}/results",
    response_model=SuccessResponse[list[ResultResponse]],
    summary="List one assessment's results",
)
async def list_results(
    organization_id: UUID,
    assessment_id: UUID,
    assessments: AssessmentSvc,
    status_filter: Annotated[ResultStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ResultResponse]]:
    """Per-control, per-target verdicts."""
    rows = await assessments.results_for(
        organization_id, assessment_id, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        data=[ResultResponse.model_validate(one) for one in rows], message="Results listed."
    )


@router.post(
    "/assessments/{assessment_id}/cancel",
    response_model=SuccessResponse[AssessmentResponse],
    summary="Cancel an assessment",
)
async def cancel_assessment(
    organization_id: UUID,
    assessment_id: UUID,
    assessments: AssessmentSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AssessmentResponse]:
    """Stop a planned or running assessment."""
    cancelled = await assessments.cancel(organization_id, assessment_id, actor_id=caller)
    return SuccessResponse(
        data=AssessmentResponse.model_validate(cancelled), message="Assessment cancelled."
    )


@router.post(
    "/scan",
    response_model=SuccessResponse[ScanResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a collector pass",
)
async def record_scan(
    organization_id: UUID,
    body: ScanRequest,
    scans: ScanRepo,
    evidence: EvidenceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ScanResponse]:
    """Record a scan and store the evidence it gathered.

    The evidence is stored as configuration snapshots so a later
    assessment can be run from it without the collector being present --
    which is what makes a historical assessment reproducible.
    """
    now = datetime.now(UTC)
    created = await scans.create(
        ComplianceScan(
            organization_id=organization_id,
            assessment_id=body.assessment_id,
            name=body.name,
            kind=ScanKind(body.kind),
            status=ScanStatus.RUNNING,
            target_type=body.target_type,
            target_id=body.target_id,
            scanner=body.scanner,
            is_incremental=body.is_incremental,
            started_at=now,
            parameters=dict(body.parameters),
            created_by=caller,
        )
    )

    for one in body.targets:
        if not one.payload:
            continue
        await evidence.collect(
            organization_id,
            kind=EvidenceKind.CONFIGURATION_SNAPSHOT,
            source=EvidenceSource.DISCOVERY,
            title=f"{body.scanner} scan of {one.name or one.target_id}",
            payload=one.payload,
            target_type=one.target_type,
            target_id=one.target_id,
            source_reference=str(created.id),
            collected_by=body.scanner,
            actor_id=caller,
        )

    created.status = ScanStatus.COMPLETED
    created.completed_at = datetime.now(UTC)
    created.targets_scanned = len(body.targets)
    created.duration_ms = (created.completed_at - now).total_seconds() * 1_000
    finished = await scans.update(created)

    await audit.record(
        organization_id,
        action=AuditAction.SCAN_STARTED,
        entity_type="scan",
        entity_id=finished.id,
        entity_reference=finished.name,
        actor_id=str(caller),
        summary=f"Recorded scan {finished.name!r} over {len(body.targets)} target(s).",
    )
    return SuccessResponse(data=ScanResponse.model_validate(finished), message="Scan recorded.")


@router.get(
    "/scans",
    response_model=SuccessResponse[list[ScanResponse]],
    summary="List scans",
)
async def list_scans(
    organization_id: UUID,
    scans: ScanRepo,
    assessment_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ScanResponse]]:
    """Scans, newest first."""
    rows = await scans.list_for_org(
        organization_id, assessment_id=assessment_id, limit=limit, offset=offset
    )
    return SuccessResponse(
        data=[ScanResponse.model_validate(one) for one in rows], message="Scans listed."
    )


@router.get(
    "/evidence",
    response_model=SuccessResponse[list[EvidenceResponse]],
    summary="List evidence",
)
async def list_evidence(
    organization_id: UUID,
    evidence: EvidenceSvc,
    control_id: UUID | None = None,
    assessment_id: UUID | None = None,
    target_id: Annotated[str | None, Query(max_length=255)] = None,
    include_superseded: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[EvidenceResponse]]:
    """Evidence, newest first. Superseded rows are excluded by default."""
    rows = await evidence.list_evidence(
        organization_id,
        control_id=control_id,
        assessment_id=assessment_id,
        target_id=target_id,
        include_superseded=include_superseded,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        data=[EvidenceResponse.model_validate(one) for one in rows],
        message="Evidence listed.",
    )


@router.post(
    "/evidence",
    response_model=SuccessResponse[EvidenceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a piece of evidence",
)
async def create_evidence(
    organization_id: UUID,
    body: EvidenceCreateRequest,
    evidence: EvidenceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[EvidenceResponse]:
    """Record proof, content-hashed at the moment it arrives."""
    created = await evidence.collect(
        organization_id,
        kind=body.kind,
        source=body.source,
        title=body.title,
        payload=body.payload,
        control_id=body.control_id,
        assessment_id=body.assessment_id,
        target_type=body.target_type,
        target_id=body.target_id,
        source_reference=body.source_reference,
        description=body.description,
        collected_by=body.collected_by,
        validity_days=body.validity_days,
        content_type=body.content_type,
        storage_key=body.storage_key,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.EVIDENCE_COLLECTED,
        entity_type="evidence",
        entity_id=created.id,
        entity_reference=created.digest,
        actor_id=str(caller),
        summary=f"Recorded evidence {created.title!r} (digest {created.digest[:12]}).",
    )
    return SuccessResponse(
        data=EvidenceResponse.model_validate(created), message="Evidence recorded."
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=SuccessResponse[EvidenceResponse],
    summary="Read one piece of evidence",
)
async def get_evidence(
    organization_id: UUID, evidence_id: UUID, evidence: EvidenceSvc
) -> SuccessResponse[EvidenceResponse]:
    """One evidence row, with its digest re-verified on the way out."""
    found = await evidence.get(organization_id, evidence_id)
    intact = evidence.verify(found)
    return SuccessResponse(
        data=EvidenceResponse.model_validate(found),
        message=(
            "Evidence read; integrity verified."
            if intact
            else (
                "Evidence read, but its payload no longer matches the digest recorded "
                "when it was collected. Treat it as compromised."
            )
        ),
    )


@router.post(
    "/evidence/{evidence_id}/supersede",
    response_model=SuccessResponse[EvidenceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Correct evidence by replacing it",
)
async def supersede_evidence(
    organization_id: UUID,
    evidence_id: UUID,
    body: EvidenceSupersedeRequest,
    evidence: EvidenceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[EvidenceResponse]:
    """Replace evidence, keeping both rows.

    There is no endpoint that edits evidence in place, and there will not
    be one: evidence that could have been edited after the fact proves
    only that a row existed.
    """
    replacement = await evidence.supersede(
        organization_id,
        evidence_id,
        payload=body.payload,
        title=body.title,
        reason=body.reason,
        collected_by=body.collected_by,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.EVIDENCE_COLLECTED,
        entity_type="evidence",
        entity_id=replacement.id,
        entity_reference=replacement.digest,
        actor_id=str(caller),
        summary=f"Superseded evidence {evidence_id} with {replacement.id}.",
        changes={"superseded": str(evidence_id), "reason": body.reason},
    )
    return SuccessResponse(
        data=EvidenceResponse.model_validate(replacement), message="Evidence superseded."
    )


@router.get(
    "/evidence/verify/all",
    response_model=SuccessResponse[dict],
    summary="Verify every evidence digest",
)
async def verify_evidence(
    organization_id: UUID,
    evidence: EvidenceSvc,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1_000,
) -> SuccessResponse[dict]:
    """Recompute every digest and report any that no longer match.

    Includes superseded rows: a tampered historical record is exactly
    what this is looking for.
    """
    report = await evidence.verify_all(organization_id, limit=limit)
    return SuccessResponse(
        data=report,
        message=(
            f"Verified {report['checked']} evidence record(s); all intact."
            if report["failed"] == 0
            else (
                f"Verified {report['checked']} evidence record(s); "
                f"{report['failed']} FAILED their integrity check."
            )
        ),
    )
