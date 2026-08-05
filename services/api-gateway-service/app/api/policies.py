"""Rate limit and quota policy management (docs/056 "RATE LIMITING", "QUOTA MANAGEMENT")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import QuotaSvc, RateLimitSvc
from app.schemas.gateway import (
    QuotaPolicyRequest,
    QuotaPolicyResponse,
    RateLimitPolicyRequest,
    RateLimitPolicyResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

rate_limits_router = APIRouter(prefix="/gateway/ratelimits", tags=["Rate Limits"])
quotas_router = APIRouter(prefix="/gateway/quotas", tags=["Quotas"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@rate_limits_router.get(
    "", response_model=SuccessResponse[list[RateLimitPolicyResponse]], summary="List rate limit policies"
)
async def list_rate_limits(
    organization_id: UUID, rate_limits: RateLimitSvc
) -> SuccessResponse[list[RateLimitPolicyResponse]]:
    """Every rate-limit policy configured in this organization."""
    rows = await rate_limits.list_policies(organization_id)
    return SuccessResponse(
        message="Rate limit policies listed.",
        data=[RateLimitPolicyResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@rate_limits_router.post(
    "",
    response_model=SuccessResponse[RateLimitPolicyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Set a rate limit policy",
)
async def set_rate_limit(
    organization_id: UUID, body: RateLimitPolicyRequest, rate_limits: RateLimitSvc
) -> SuccessResponse[RateLimitPolicyResponse]:
    """Create or replace the rate-limit policy for a given scope."""
    created = await rate_limits.set_policy(
        organization_id,
        scope=body.scope,
        scope_reference=body.scope_reference,
        max_requests=body.max_requests,
        window_seconds=body.window_seconds,
        algorithm=body.algorithm,
        burst_max_requests=body.burst_max_requests,
        burst_window_seconds=body.burst_window_seconds,
    )
    return SuccessResponse(
        message="Rate limit policy set.",
        data=RateLimitPolicyResponse.model_validate(created),
        meta=_meta(),
    )


@quotas_router.get(
    "", response_model=SuccessResponse[list[QuotaPolicyResponse]], summary="List quota policies"
)
async def list_quotas(
    organization_id: UUID, quotas: QuotaSvc
) -> SuccessResponse[list[QuotaPolicyResponse]]:
    """Every quota configured in this organization."""
    rows = await quotas.list_policies(organization_id)
    return SuccessResponse(
        message="Quota policies listed.",
        data=[QuotaPolicyResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@quotas_router.post(
    "",
    response_model=SuccessResponse[QuotaPolicyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Set a quota policy",
)
async def set_quota(
    organization_id: UUID, body: QuotaPolicyRequest, quotas: QuotaSvc
) -> SuccessResponse[QuotaPolicyResponse]:
    """Create or replace the quota for a given scope/kind."""
    created = await quotas.set_policy(
        organization_id,
        scope=body.scope,
        scope_reference=body.scope_reference,
        kind=body.kind,
        period=body.period,
        limit_value=body.limit_value,
    )
    return SuccessResponse(
        message="Quota policy set.", data=QuotaPolicyResponse.model_validate(created), meta=_meta()
    )


__all__ = ["quotas_router", "rate_limits_router"]
