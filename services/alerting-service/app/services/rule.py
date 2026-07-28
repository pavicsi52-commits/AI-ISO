"""Alert rule CRUD, including its own inline conditions.

Conditions are created with their owning rule rather than through a
separate endpoint -- they have no meaning apart from it (see
:class:`~app.schemas.rule.AlertConditionCreateRequest`'s own docstring).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared_core.enums.severity import Severity

from app.models.alert_condition import AlertCondition
from app.models.alert_rule import AlertRule
from app.models.enums import AlertRuleType, AlertSource, BooleanOperator
from app.repositories.alert_condition import AlertConditionRepository
from app.repositories.alert_rule import AlertRuleRepository
from app.schemas.rule import AlertConditionCreateRequest


class AlertRuleService:
    """Creates and reads alert rules together with their own conditions."""

    def __init__(self, rules: AlertRuleRepository, conditions: AlertConditionRepository) -> None:
        self._rules = rules
        self._conditions = conditions

    async def get_by_id(self, rule_id: UUID) -> AlertRule:
        """Return the rule identified by *rule_id*.

        Raises:
            NotFoundError: If no such rule exists.
        """
        return await self._rules.require_by_id(rule_id)

    async def list_for_org(self, organization_id: UUID) -> list[AlertRule]:
        """Every alert rule belonging to *organization_id*."""
        return await self._rules.list_for_org(organization_id)

    async def list_enabled_for_source(
        self, organization_id: UUID, source: AlertSource
    ) -> list[AlertRule]:
        """Every enabled rule matching *source*."""
        return await self._rules.list_enabled_for_source(organization_id, source)

    async def list_conditions(self, rule_id: UUID) -> list[AlertCondition]:
        """Every condition attached to *rule_id*, in evaluation order."""
        return await self._conditions.list_for_rule(rule_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        rule_type: AlertRuleType,
        source: AlertSource,
        boolean_operator: BooleanOperator,
        severity: Severity,
        window_seconds: float | None,
        tags: dict[str, str],
        enabled: bool,
        conditions: Sequence[AlertConditionCreateRequest],
    ) -> tuple[AlertRule, list[AlertCondition]]:
        """Create a rule and its own conditions, returning both."""
        rule = await self._rules.create(
            AlertRule(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                description=description,
                rule_type=rule_type,
                source=source,
                boolean_operator=boolean_operator,
                severity=severity,
                window_seconds=window_seconds,
                tags=tags,
                enabled=enabled,
            )
        )
        created = [
            await self._conditions.create(
                AlertCondition(
                    organization_id=organization_id,
                    project_id=project_id,
                    rule_id=rule.id,
                    sequence=condition.sequence,
                    metric_name=condition.metric_name,
                    expression=condition.expression,
                )
            )
            for condition in conditions
        ]
        return rule, created


__all__ = ["AlertRuleService"]
