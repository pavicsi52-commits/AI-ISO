"""Request/response schemas for ``/alert-rules``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.enums.severity import Severity

from app.models.enums import AlertRuleType, AlertSource, BooleanOperator


class AlertConditionCreateRequest(BaseModel):
    """One condition supplied inline when creating a rule.

    Conditions have no REST surface of their own -- they are only ever
    meaningful as part of the rule that owns them, so they are created
    with it rather than through a separate endpoint.
    """

    sequence: int = 0
    metric_name: str | None = Field(default=None, max_length=255)
    expression: str = Field(min_length=1)


class AlertRuleCreateRequest(BaseModel):
    """Body of ``POST /alert-rules``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_type: AlertRuleType
    source: AlertSource
    boolean_operator: BooleanOperator = BooleanOperator.AND
    severity: Severity = Severity.MEDIUM
    window_seconds: float | None = Field(default=None, gt=0)
    tags: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    conditions: list[AlertConditionCreateRequest] = Field(default_factory=list)


class AlertConditionResponse(BaseModel):
    """One condition attached to a rule."""

    id: UUID
    rule_id: UUID
    sequence: int
    metric_name: str | None
    expression: str


class AlertRuleResponse(BaseModel):
    """One rule engine definition, with its own conditions."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    description: str | None
    rule_type: AlertRuleType
    source: AlertSource
    boolean_operator: BooleanOperator
    severity: Severity
    window_seconds: float | None
    tags: dict[str, str]
    enabled: bool
    conditions: list[AlertConditionResponse]


__all__ = [
    "AlertConditionCreateRequest",
    "AlertConditionResponse",
    "AlertRuleCreateRequest",
    "AlertRuleResponse",
]
