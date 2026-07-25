"""Tests for reusable outbound response DTOs."""

from __future__ import annotations

from uuid import uuid4

from shared_core.enums import HealthStatus, JobStatus, ValidationStatus
from shared_core.responses import (
    DependencyCheck,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    JobResponse,
    ListResponse,
    PaginatedResponse,
    ReadinessResponse,
    SuccessResponse,
)
from shared_core.responses.validation import ValidationResponse
from shared_core.schemas import PaginationMeta, ResponseMeta


def test_success_response_wraps_arbitrary_data() -> None:
    response = SuccessResponse[dict](
        message="ok",
        data={"key": "value"},
        meta=ResponseMeta(request_id="req-1"),
    )

    assert response.success is True
    assert response.data == {"key": "value"}


def test_error_response_carries_structured_error() -> None:
    response = ErrorResponse(
        message="Validation failed.",
        error=ErrorDetail(code="AIIOS-VAL-0001", details=["name is required"]),
        meta=ResponseMeta(request_id="req-1"),
    )

    assert response.success is False
    assert response.error.code == "AIIOS-VAL-0001"
    assert response.error.details == ["name is required"]


def test_list_response_holds_items_and_count() -> None:
    response = ListResponse[str](items=["a", "b", "c"], count=3)

    assert response.count == 3
    assert len(response.items) == 3


def test_paginated_response_combines_items_and_pagination_meta() -> None:
    pagination = PaginationMeta(page=1, page_size=10, total=3, has_next=False, has_previous=False)
    response = PaginatedResponse[str](items=["a", "b", "c"], pagination=pagination)

    assert response.pagination.total == 3


def test_job_response_carries_id_and_status() -> None:
    job_id = uuid4()
    response = JobResponse(job_id=job_id, status=JobStatus.RUNNING)

    assert response.job_id == job_id
    assert response.status == JobStatus.RUNNING


def test_health_response_shape() -> None:
    response = HealthResponse(
        status=HealthStatus.HEALTHY, service="gateway", version="0.1.0", environment="production"
    )

    assert response.status == HealthStatus.HEALTHY


def test_readiness_response_aggregates_dependency_checks() -> None:
    response = ReadinessResponse(
        status=HealthStatus.HEALTHY,
        checks=[DependencyCheck(name="database", status=HealthStatus.HEALTHY)],
    )

    assert response.checks[0].name == "database"


def test_validation_response_defaults_to_empty_errors_and_warnings() -> None:
    response = ValidationResponse(status=ValidationStatus.VALID)

    assert response.errors == []
    assert response.warnings == []
