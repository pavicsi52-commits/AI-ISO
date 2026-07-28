"""Rule engine catalog CRUD ("RULE ENGINE" "Support")."""

from __future__ import annotations

from uuid import UUID

from shared_core.monitoring.thresholds import ThresholdLevel

from app.models.enums import MonitoringRuleType
from app.models.monitoring_rule import MonitoringRule
from app.repositories.monitoring_rule import MonitoringRuleRepository


class MonitoringRuleService:
    """Creates and reads rule engine conditions."""

    def __init__(self, rules: MonitoringRuleRepository) -> None:
        self._rules = rules

    async def get_by_id(self, rule_id: UUID) -> MonitoringRule:
        """Return the rule identified by *rule_id*.

        Raises:
            NotFoundError: If no such rule exists.
        """
        return await self._rules.require_by_id(rule_id)

    async def list_for_metric(self, metric_id: UUID) -> list[MonitoringRule]:
        """Every active rule scoped to *metric_id*."""
        return await self._rules.list_for_metric(metric_id)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringRule]:
        """Every rule belonging to *organization_id*."""
        return await self._rules.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        metric_id: UUID | None,
        rule_type: MonitoringRuleType,
        name: str,
        description: str | None,
        condition: str,
        severity: ThresholdLevel,
        window_seconds: float | None,
        escalation_after_seconds: float | None,
    ) -> MonitoringRule:
        """Register a new rule engine condition."""
        return await self._rules.create(
            MonitoringRule(
                organization_id=organization_id,
                metric_id=metric_id,
                rule_type=rule_type,
                name=name,
                description=description,
                condition=condition,
                severity=severity,
                window_seconds=window_seconds,
                escalation_after_seconds=escalation_after_seconds,
            )
        )


__all__ = ["MonitoringRuleService"]
