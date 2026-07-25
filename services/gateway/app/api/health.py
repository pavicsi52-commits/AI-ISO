"""Health, readiness, and liveness endpoints.

Required on every AI-IOS service per
``docs/008_Enterprise_Backend_Master_Architecture.md.txt``. These endpoints
carry no business logic.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.config.settings import Settings, get_settings
from app.schemas.health import HealthStatus, LivenessStatus, ReadinessCheck, ReadinessStatus
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Health"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/health",
    response_model=SuccessResponse[HealthStatus],
    summary="Overall service health",
    description="Returns the gateway's health status, service name, version, and environment.",
)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse[HealthStatus]:
    """Return the overall health of the gateway service."""
    data = HealthStatus(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
    return SuccessResponse(message="Service is healthy.", data=data, meta=_meta())


@router.get(
    "/liveness",
    response_model=SuccessResponse[LivenessStatus],
    summary="Process liveness probe",
    description="Returns 200 as long as the process is running and able to serve traffic.",
)
async def liveness() -> SuccessResponse[LivenessStatus]:
    """Return whether the process is alive. Used by Kubernetes liveness probes."""
    return SuccessResponse(
        message="Service is alive.",
        data=LivenessStatus(status="alive"),
        meta=_meta(),
    )


@router.get(
    "/readiness",
    response_model=SuccessResponse[ReadinessStatus],
    summary="Readiness probe",
    description="Returns whether the gateway has completed startup and is ready for traffic.",
)
async def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessResponse[ReadinessStatus]:
    """Return whether the gateway is ready to receive traffic.

    The foundation-phase gateway owns no external dependencies (database,
    cache, broker), so readiness reduces to confirming configuration loaded
    successfully. Future phases add real dependency checks here.
    """
    config_status: Literal["ok", "failed"] = "ok" if settings.app_name else "failed"
    data = ReadinessStatus(
        status="ready",
        checks=[ReadinessCheck(name="configuration", status=config_status)],
    )
    return SuccessResponse(message="Service is ready.", data=data, meta=_meta())
