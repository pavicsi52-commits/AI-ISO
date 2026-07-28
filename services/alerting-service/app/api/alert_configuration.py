"""``/alert-routes``, ``/alert-escalation-policies``, and
``/alert-suppressions`` -- the three configuration surfaces docs/045's
own literal REST list omits despite naming Routing, Escalation, and
Suppression as explicit ACCEPTANCE CRITERIA. See each schema module's
own docstring for the reasoning.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, EscalationSvc, RouteSvc, SuppressionSvc
from app.escalation.engine import parse_levels
from app.models.alert_escalation import AlertEscalationPolicy
from app.models.alert_route import AlertRoute
from app.models.alert_suppression import AlertSuppression
from app.schemas.escalation import (
    EscalationLevelResponse,
    EscalationPolicyCreateRequest,
    EscalationPolicyResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.route import AlertRouteCreateRequest, AlertRouteResponse
from app.schemas.suppression import SuppressionCreateRequest, SuppressionResponse

routes_router = APIRouter(prefix="/alert-routes", tags=["Alert Routes"])
escalation_router = APIRouter(
    prefix="/alert-escalation-policies", tags=["Alert Escalation Policies"]
)
suppression_router = APIRouter(prefix="/alert-suppressions", tags=["Alert Suppressions"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def route_to_response(route: AlertRoute) -> AlertRouteResponse:
    """Map an :class:`AlertRoute` row onto its own response schema."""
    return AlertRouteResponse(
        id=route.id,
        organization_id=route.organization_id,
        project_id=route.project_id,
        name=route.name,
        channel=route.channel,
        target_type=route.target_type,
        target_reference=route.target_reference,
        configuration=route.configuration,
        severity_filter=route.severity_filter,
        enabled=route.enabled,
    )


def policy_to_response(policy: AlertEscalationPolicy) -> EscalationPolicyResponse:
    """Map an :class:`AlertEscalationPolicy` row onto its own response schema.

    Levels are returned *validated*, with their own resolved cumulative
    delays -- so a caller sees exactly what the engine will act on,
    including that a malformed level was dropped.
    """
    return EscalationPolicyResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        project_id=policy.project_id,
        name=policy.name,
        levels=[
            EscalationLevelResponse(
                sequence=level.sequence,
                target_type=level.target_type,
                target_reference=level.target_reference,
                delay_seconds=level.delay_seconds,
                cumulative_delay_seconds=level.cumulative_delay_seconds,
            )
            for level in parse_levels(policy.levels)
        ],
        enabled=policy.enabled,
    )


def suppression_to_response(suppression: AlertSuppression) -> SuppressionResponse:
    """Map an :class:`AlertSuppression` row onto its own response schema."""
    return SuppressionResponse(
        id=suppression.id,
        organization_id=suppression.organization_id,
        project_id=suppression.project_id,
        suppression_type=suppression.suppression_type,
        scope_reference=suppression.scope_reference,
        reason=suppression.reason,
        created_by=suppression.created_by,
        starts_at=suppression.starts_at,
        ends_at=suppression.ends_at,
        enabled=suppression.enabled,
    )


@routes_router.get("", response_model=SuccessResponse[list[AlertRouteResponse]])
async def list_alert_routes(
    organization_id: UUID, routes: RouteSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertRouteResponse]]:
    """List every routing configuration for an organization."""
    records = await routes.list_for_org(organization_id)
    data = [route_to_response(record) for record in records]
    return SuccessResponse(message="Alert routes retrieved.", data=data, meta=_meta())


@routes_router.post("", response_model=SuccessResponse[AlertRouteResponse], status_code=201)
async def create_alert_route(
    body: AlertRouteCreateRequest, routes: RouteSvc, _caller: CurrentUserId
) -> SuccessResponse[AlertRouteResponse]:
    """Create a routing configuration."""
    route = await routes.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        channel=body.channel,
        target_type=body.target_type,
        target_reference=body.target_reference,
        configuration=body.configuration,
        severity_filter=body.severity_filter,
        enabled=body.enabled,
    )
    return SuccessResponse(
        message="Alert route created.", data=route_to_response(route), meta=_meta()
    )


@escalation_router.get("", response_model=SuccessResponse[list[EscalationPolicyResponse]])
async def list_escalation_policies(
    organization_id: UUID, policies: EscalationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[EscalationPolicyResponse]]:
    """List every escalation policy for an organization."""
    records = await policies.list_for_org(organization_id)
    data = [policy_to_response(record) for record in records]
    return SuccessResponse(message="Escalation policies retrieved.", data=data, meta=_meta())


@escalation_router.post(
    "", response_model=SuccessResponse[EscalationPolicyResponse], status_code=201
)
async def create_escalation_policy(
    body: EscalationPolicyCreateRequest, policies: EscalationSvc, _caller: CurrentUserId
) -> SuccessResponse[EscalationPolicyResponse]:
    """Create an escalation policy from an ordered level chain."""
    policy = await policies.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        levels=body.levels,
        enabled=body.enabled,
    )
    return SuccessResponse(
        message="Escalation policy created.", data=policy_to_response(policy), meta=_meta()
    )


@suppression_router.get("", response_model=SuccessResponse[list[SuppressionResponse]])
async def list_suppressions(
    organization_id: UUID, suppressions: SuppressionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[SuppressionResponse]]:
    """List every suppression rule for an organization."""
    records = await suppressions.list_for_org(organization_id)
    data = [suppression_to_response(record) for record in records]
    return SuccessResponse(message="Alert suppressions retrieved.", data=data, meta=_meta())


@suppression_router.post("", response_model=SuccessResponse[SuppressionResponse], status_code=201)
async def create_suppression(
    body: SuppressionCreateRequest, suppressions: SuppressionSvc, _caller: CurrentUserId
) -> SuccessResponse[SuppressionResponse]:
    """Create a suppression rule."""
    suppression = await suppressions.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        suppression_type=body.suppression_type,
        scope_reference=body.scope_reference,
        reason=body.reason,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        enabled=body.enabled,
    )
    return SuccessResponse(
        message="Alert suppression created.",
        data=suppression_to_response(suppression),
        meta=_meta(),
    )


__all__ = [
    "escalation_router",
    "policy_to_response",
    "route_to_response",
    "routes_router",
    "suppression_router",
    "suppression_to_response",
]
