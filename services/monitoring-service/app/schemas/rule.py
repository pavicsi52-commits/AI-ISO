"""Request/response schemas for the rule engine's own rule catalog."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.monitoring.thresholds import ThresholdLevel

from app.models.enums import MonitoringRuleType


class MonitoringRuleCreateRequest(BaseModel):
    """Body of a request to create a rule against a metric's own collected data."""

    organization_id: UUID
    metric_id: UUID | None = None
    rule_type: MonitoringRuleType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    condition: str = Field(min_length=1)
    severity: ThresholdLevel = ThresholdLevel.MEDIUM
    window_seconds: float | None = Field(default=None, gt=0)
    escalation_after_seconds: float | None = Field(default=None, gt=0)


class MonitoringRuleResponse(BaseModel):
    """One rule engine condition against a metric's own collected data."""

    id: UUID
    organization_id: UUID
    metric_id: UUID | None
    rule_type: MonitoringRuleType
    name: str
    description: str | None
    condition: str
    severity: ThresholdLevel
    window_seconds: float | None
    escalation_after_seconds: float | None
    is_active: bool


__all__ = ["MonitoringRuleCreateRequest", "MonitoringRuleResponse"]
