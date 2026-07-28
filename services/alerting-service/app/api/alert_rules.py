"""``/alert-rules`` -- the rule engine catalog."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RuleSvc
from app.models.alert_condition import AlertCondition
from app.models.alert_rule import AlertRule
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.rule import (
    AlertConditionResponse,
    AlertRuleCreateRequest,
    AlertRuleResponse,
)

router = APIRouter(prefix="/alert-rules", tags=["Alert Rules"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _condition_to_response(condition: AlertCondition) -> AlertConditionResponse:
    return AlertConditionResponse(
        id=condition.id,
        rule_id=condition.rule_id,
        sequence=condition.sequence,
        metric_name=condition.metric_name,
        expression=condition.expression,
    )


def rule_to_response(rule: AlertRule, conditions: list[AlertCondition]) -> AlertRuleResponse:
    """Map an :class:`AlertRule` and its own conditions onto the response schema."""
    return AlertRuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        project_id=rule.project_id,
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type,
        source=rule.source,
        boolean_operator=rule.boolean_operator,
        severity=rule.severity,
        window_seconds=rule.window_seconds,
        tags=rule.tags,
        enabled=rule.enabled,
        conditions=[_condition_to_response(condition) for condition in conditions],
    )


@router.get("", response_model=SuccessResponse[list[AlertRuleResponse]])
async def list_alert_rules(
    organization_id: UUID, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AlertRuleResponse]]:
    """List every alert rule for an organization, with its own conditions."""
    records = await rules.list_for_org(organization_id)
    data = [rule_to_response(record, await rules.list_conditions(record.id)) for record in records]
    return SuccessResponse(message="Alert rules retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[AlertRuleResponse], status_code=201)
async def create_alert_rule(
    body: AlertRuleCreateRequest, rules: RuleSvc, _caller: CurrentUserId
) -> SuccessResponse[AlertRuleResponse]:
    """Create an alert rule together with its own conditions."""
    rule, conditions = await rules.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        rule_type=body.rule_type,
        source=body.source,
        boolean_operator=body.boolean_operator,
        severity=body.severity,
        window_seconds=body.window_seconds,
        tags=body.tags,
        enabled=body.enabled,
        conditions=body.conditions,
    )
    return SuccessResponse(
        message="Alert rule created.", data=rule_to_response(rule, conditions), meta=_meta()
    )


__all__ = ["router", "rule_to_response"]
