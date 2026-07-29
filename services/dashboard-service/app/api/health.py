"""Health, readiness, and liveness endpoints.

Required on every AI-IOS service per docs/008. Readiness checks the
database, plus the Neo4j graph behind topology widgets when it is
configured. The graph is *reported* but does not gate readiness:
topology is one widget type among eighteen, and refusing all traffic
because Neo4j is down would take out every dashboard that never touches
it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from shared_core.database.health import check_database_health
from shared_core.enums.health_status import HealthStatus as HealthStatusEnum
from shared_core.logging.context import get_log_context
from shared_core.monitoring.status import calculate_status

from app.config.settings import Settings, get_settings
from app.schemas.health import HealthStatus, LivenessStatus, ReadinessCheck, ReadinessStatus
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Health"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/health", response_model=SuccessResponse[HealthStatus], summary="Overall service health"
)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse[HealthStatus]:
    """Return the overall health of the dashboard service."""
    data = HealthStatus(
        status="healthy",
        service=settings.application.app_name,
        version=settings.application.app_version,
        environment=settings.application.environment.value,
    )
    return SuccessResponse(message="Service is healthy.", data=data, meta=_meta())


@router.get(
    "/liveness",
    response_model=SuccessResponse[LivenessStatus],
    summary="Process liveness probe",
)
async def liveness() -> SuccessResponse[LivenessStatus]:
    """Return whether the process is alive. Used by Kubernetes liveness probes."""
    return SuccessResponse(
        message="Service is alive.", data=LivenessStatus(status="alive"), meta=_meta()
    )


@router.get(
    "/readiness", response_model=SuccessResponse[ReadinessStatus], summary="Readiness probe"
)
async def readiness(request: Request) -> SuccessResponse[ReadinessStatus]:
    """Return whether the service and its dependencies are ready for traffic."""
    db_status, db_latency_ms = await check_database_health(request.app.state.db_engine)
    checks = [
        ReadinessCheck(
            name="database",
            status="ok" if db_status == HealthStatusEnum.HEALTHY else "failed",
            detail=f"{db_latency_ms:.1f}ms",
        )
    ]

    # The graph is reported but does not gate readiness: topology is one
    # widget type among eighteen, and refusing all traffic because Neo4j
    # is down would take out every dashboard that never touches it.
    driver = getattr(request.app.state, "neo4j_driver", None)
    if driver is not None:
        checks.append(await _check_graph(driver))

    overall = calculate_status([db_status])
    data = ReadinessStatus(
        status="ready" if overall == HealthStatusEnum.HEALTHY else "not_ready", checks=checks
    )
    return SuccessResponse(message="Readiness computed.", data=data, meta=_meta())


async def _check_graph(driver: object) -> ReadinessCheck:
    """Probe the Neo4j driver behind the topology widgets."""
    try:
        await driver.verify_connectivity()  # type: ignore[attr-defined]
    except Exception as exc:
        return ReadinessCheck(name="graph", status="failed", detail=str(exc))
    return ReadinessCheck(name="graph", status="ok", detail="topology available")


__all__ = ["router"]
