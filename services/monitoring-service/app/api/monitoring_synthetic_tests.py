"""``/monitoring-synthetic-tests``. No REST list entry of its own in
docs/044 -- added directly: "Synthetic Monitoring" is an explicit
ACCEPTANCE CRITERIA line, and without some way to register a synthetic
test, "Scheduled Tests" would have nothing to schedule.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SyntheticTestSvc
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.synthetic_test import (
    MonitoringSyntheticTestCreateRequest,
    MonitoringSyntheticTestResponse,
)

router = APIRouter(prefix="/monitoring-synthetic-tests", tags=["Monitoring Synthetic Tests"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def synthetic_test_to_response(
    test: MonitoringSyntheticTest,
) -> MonitoringSyntheticTestResponse:
    return MonitoringSyntheticTestResponse(
        id=test.id,
        organization_id=test.organization_id,
        target_id=test.target_id,
        check_type=test.check_type,
        name=test.name,
        parameters=test.parameters,
        interval_seconds=test.interval_seconds,
        is_active=test.is_active,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringSyntheticTestResponse]])
async def list_synthetic_tests(
    organization_id: UUID, tests: SyntheticTestSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringSyntheticTestResponse]]:
    """List every synthetic test belonging to *organization_id*."""
    records = await tests.list_for_org(organization_id)
    data = [synthetic_test_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring synthetic tests retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringSyntheticTestResponse], status_code=201)
async def create_synthetic_test(
    body: MonitoringSyntheticTestCreateRequest, tests: SyntheticTestSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringSyntheticTestResponse]:
    """Register a new scheduled synthetic check."""
    test = await tests.create(
        organization_id=body.organization_id,
        target_id=body.target_id,
        check_type=body.check_type,
        name=body.name,
        parameters=body.parameters,
        interval_seconds=body.interval_seconds,
        is_active=body.is_active,
    )
    return SuccessResponse(
        message="Monitoring synthetic test registered.",
        data=synthetic_test_to_response(test),
        meta=_meta(),
    )


__all__ = ["router", "synthetic_test_to_response"]
