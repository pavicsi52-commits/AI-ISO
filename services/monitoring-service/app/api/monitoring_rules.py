"""``/monitoring-rules``. No REST list entry of its own in docs/044 --
added directly for consistency and completeness, matching
:mod:`app.api.monitoring_thresholds`'s own analogous surface for the
adjacent "RULE ENGINE" section.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RuleSvc
from app.models.monitoring_rule import MonitoringRule
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.rule import MonitoringRuleCreateRequest, MonitoringRuleResponse

router = APIRouter(prefix="/monitoring-rules", tags=["Monitoring Rules"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def rule_to_response(rule: MonitoringRule) -> MonitoringRuleResponse:
    return MonitoringRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        metric_id=rule.metric_id,
        rule_type=rule.rule_type,
        name=rule.name,
        description=rule.description,
        condition=rule.condition,
        severity=rule.severity,
        window_seconds=rule.window_seconds,
        escalation_after_seconds=rule.escalation_after_seconds,
        is_active=rule.is_active,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringRuleResponse]])
async def list_rules(
    organization_id: UUID, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringRuleResponse]]:
    """List every rule belonging to *organization_id*."""
    records = await rules.list_for_org(organization_id)
    data = [rule_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring rules retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringRuleResponse], status_code=201)
async def create_rule(
    body: MonitoringRuleCreateRequest, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringRuleResponse]:
    """Register a new rule engine condition."""
    rule = await rules.create(
        organization_id=body.organization_id,
        metric_id=body.metric_id,
        rule_type=body.rule_type,
        name=body.name,
        description=body.description,
        condition=body.condition,
        severity=body.severity,
        window_seconds=body.window_seconds,
        escalation_after_seconds=body.escalation_after_seconds,
    )
    return SuccessResponse(
        message="Monitoring rule created.", data=rule_to_response(rule), meta=_meta()
    )


__all__ = ["router", "rule_to_response"]
