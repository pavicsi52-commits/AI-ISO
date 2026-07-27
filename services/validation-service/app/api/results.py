"""``/validation-results`` and its ``failures``/``exceptions``/
``executions`` actions.

``GET /validation-results``/``GET /validation-results/{id}`` are per
docs/043's own literal REST list. The ``failures``/``exceptions``
actions underneath a result, and the ``executions/{id}``/
``executions/{id}/score`` actions, all have no REST list entry of
their own -- added directly, the same "required capability with no
REST list entry" precedent ``services/workflow-runtime-service``'s own
approval-decision endpoints already established. Without the
``executions`` actions specifically, docs/043's own explicit "Scoring"
ACCEPTANCE CRITERIA line would compute and persist a real weighted
score every run yet expose it through no REST surface at all -- the
same "orphaned capability, found via coverage" gap
``services/workflow-runtime-service``'s own ``WorkflowEventRecord``
table already hit once before.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ExceptionSvc, ExecutionSvc, FailureSvc, ResultSvc, ScoreSvc
from app.api.validations import execution_to_response
from app.models.validation_exception import ValidationException
from app.models.validation_failure import ValidationFailure
from app.models.validation_result import ValidationResult
from app.models.validation_score import ValidationScore
from app.schemas.exception import (
    ValidationExceptionDecisionRequest,
    ValidationExceptionRequest,
    ValidationExceptionResponse,
)
from app.schemas.execution import ValidationExecutionResponse
from app.schemas.failure import ValidationFailureResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.result import ValidationResultDetailResponse, ValidationResultResponse
from app.schemas.score import ValidationScoreResponse

router = APIRouter(prefix="/validation-results", tags=["Validation Results"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _result_to_response(
    result: ValidationResult, results: ResultSvc
) -> ValidationResultResponse:
    details = await results.list_details(result.id)
    return ValidationResultResponse(
        id=result.id,
        organization_id=result.organization_id,
        execution_id=result.execution_id,
        target_id=result.target_id,
        check_id=result.check_id,
        check_type=result.check_type,
        rule_id=result.rule_id,
        status=result.status,
        message=result.message,
        evaluated_at=result.evaluated_at,
        duration_ms=result.duration_ms,
        details=[
            ValidationResultDetailResponse(id=detail.id, key=detail.key, value=detail.value)
            for detail in details
        ],
    )


def failure_to_response(failure: ValidationFailure) -> ValidationFailureResponse:
    return ValidationFailureResponse(
        id=failure.id,
        organization_id=failure.organization_id,
        result_id=failure.result_id,
        severity=failure.severity,
        reason=failure.reason,
        is_resolved=failure.is_resolved,
        resolved_at=failure.resolved_at,
        resolved_by=failure.resolved_by,
    )


def score_to_response(score: ValidationScore) -> ValidationScoreResponse:
    return ValidationScoreResponse(
        id=score.id,
        execution_id=score.execution_id,
        overall_score=score.overall_score,
        infrastructure_score=score.infrastructure_score,
        security_score=score.security_score,
        compliance_score=score.compliance_score,
        configuration_score=score.configuration_score,
        performance_score=score.performance_score,
        health_score=score.health_score,
        computed_at=score.computed_at,
    )


def exception_to_response(exception: ValidationException) -> ValidationExceptionResponse:
    return ValidationExceptionResponse(
        id=exception.id,
        organization_id=exception.organization_id,
        failure_id=exception.failure_id,
        reason=exception.reason,
        status=exception.status,
        requested_by=exception.requested_by,
        decided_by=exception.decided_by,
        decided_at=exception.decided_at,
        decision_reason=exception.decision_reason,
        expires_at=exception.expires_at,
    )


@router.get("", response_model=SuccessResponse[list[ValidationResultResponse]])
async def list_validation_results(
    results: ResultSvc,
    _caller: CurrentUserId,
    execution_id: UUID | None = None,
    target_id: UUID | None = None,
) -> SuccessResponse[list[ValidationResultResponse]]:
    """List validation results, filtered by *execution_id* or *target_id*."""
    if execution_id is not None:
        records = await results.list_for_execution(execution_id)
    elif target_id is not None:
        records = await results.list_for_target(target_id)
    else:
        records = []
    data = [await _result_to_response(record, results) for record in records]
    return SuccessResponse(message="Validation results retrieved.", data=data, meta=_meta())


@router.get("/{result_id}", response_model=SuccessResponse[ValidationResultResponse])
async def get_validation_result(
    result_id: UUID, results: ResultSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationResultResponse]:
    """Return one validation result.

    Raises:
        NotFoundError: If no such result exists.
    """
    result = await results.get_by_id(result_id)
    data = await _result_to_response(result, results)
    return SuccessResponse(message="Validation result retrieved.", data=data, meta=_meta())


@router.get(
    "/executions/{execution_id}", response_model=SuccessResponse[ValidationExecutionResponse]
)
async def get_validation_execution(
    execution_id: UUID, execution: ExecutionSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationExecutionResponse]:
    """Return one validation execution.

    Raises:
        NotFoundError: If no such execution exists.
    """
    record = await execution.get_by_id(execution_id)
    return SuccessResponse(
        message="Validation execution retrieved.",
        data=execution_to_response(record),
        meta=_meta(),
    )


@router.get(
    "/executions/{execution_id}/score", response_model=SuccessResponse[ValidationScoreResponse]
)
async def get_validation_execution_score(
    execution_id: UUID, scores: ScoreSvc, _caller: CurrentUserId
) -> SuccessResponse[ValidationScoreResponse]:
    """Return one validation execution's own weighted score ("Scoring").

    Raises:
        NotFoundError: If *execution_id* has no score computed yet.
    """
    score = await scores.get_for_execution(execution_id)
    if score is None:
        raise NotFoundError(f"Validation execution {execution_id!r} has no score computed yet.")
    return SuccessResponse(
        message="Validation execution score retrieved.",
        data=score_to_response(score),
        meta=_meta(),
    )


@router.get(
    "/{result_id}/failures", response_model=SuccessResponse[list[ValidationFailureResponse]]
)
async def list_result_failures(
    result_id: UUID, failures: FailureSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationFailureResponse]]:
    """List every failure recorded for a validation result."""
    records = await failures.list_for_result(result_id)
    data = [failure_to_response(record) for record in records]
    return SuccessResponse(message="Validation failures retrieved.", data=data, meta=_meta())


@router.post(
    "/failures/{failure_id}/exceptions",
    response_model=SuccessResponse[ValidationExceptionResponse],
    status_code=201,
)
async def request_validation_exception(
    failure_id: UUID,
    body: ValidationExceptionRequest,
    failures: FailureSvc,
    exceptions: ExceptionSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ValidationExceptionResponse]:
    """Request a waiver for a known validation failure ("Validation Exceptions").

    Raises:
        NotFoundError: If no such failure exists.
    """
    failure = await failures.get_by_id(failure_id)
    exception = await exceptions.request(
        organization_id=failure.organization_id,
        failure_id=failure.id,
        reason=body.reason,
        requested_by=caller,
        expires_at=body.expires_at,
    )
    return SuccessResponse(
        message="Validation exception requested.",
        data=exception_to_response(exception),
        meta=_meta(),
    )


@router.get(
    "/failures/{failure_id}/exceptions",
    response_model=SuccessResponse[list[ValidationExceptionResponse]],
)
async def list_failure_exceptions(
    failure_id: UUID, exceptions: ExceptionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ValidationExceptionResponse]]:
    """List every exception ever requested for a validation failure."""
    records = await exceptions.list_for_failure(failure_id)
    data = [exception_to_response(record) for record in records]
    return SuccessResponse(message="Validation exceptions retrieved.", data=data, meta=_meta())


@router.post(
    "/failures/{failure_id}/exceptions/{exception_id}/decide",
    response_model=SuccessResponse[ValidationExceptionResponse],
)
async def decide_validation_exception(
    failure_id: UUID,
    exception_id: UUID,
    body: ValidationExceptionDecisionRequest,
    exceptions: ExceptionSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ValidationExceptionResponse]:
    """Approve or reject a pending exception request.

    Raises:
        NotFoundError: If no such exception exists.
        ConflictError: If it has already been decided.
    """
    del failure_id  # scoping context only; exception_id alone identifies the row
    exception = await exceptions.decide(
        exception_id,
        approve=body.approve,
        decided_by=caller,
        decision_reason=body.decision_reason,
    )
    return SuccessResponse(
        message="Validation exception decided.", data=exception_to_response(exception), meta=_meta()
    )


__all__ = ["exception_to_response", "failure_to_response", "router", "score_to_response"]
