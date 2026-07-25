"""Discovery rule management and evaluation. Per docs/037 "DISCOVERY
RULES": Include Rules, Exclude Rules, Filters, Asset Matching,
Classification Rules, Relationship Rules, Tag Assignment, Owner
Assignment, Project Assignment. No REST surface of its own -- docs/037's
own literal REST list never names a ``/discovery/rules`` endpoint;
rules are evaluated internally by ``app/services/discovery_execution.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.discovery_rule import DiscoveryRule
from app.models.enums import RuleType
from app.repositories.discovery_rule import DiscoveryRuleRepository


def matches_rule(rule: DiscoveryRule, candidate_value: str | None) -> bool:
    """Evaluate a simple ``{field, operator, value}`` rule against
    *candidate_value* -- only ``eq``/``ne``/``contains`` are supported,
    the same "documented scope limit, not a silent gap"
    ``services/inventory-service``'s own ``AssetGroupService`` rule
    evaluator already established for dimensions a full query-builder
    would be needed to cover completely.
    """
    if candidate_value is None:
        return False
    if rule.operator == "eq":
        return bool(candidate_value == rule.value)
    if rule.operator == "ne":
        return bool(candidate_value != rule.value)
    if rule.operator == "contains":
        return str(rule.value) in candidate_value
    return False


class DiscoveryRuleService:
    """Creates and lists include/exclude/classification/relationship/
    assignment rules.
    """

    def __init__(self, rules: DiscoveryRuleRepository) -> None:
        self._rules = rules

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryRule]:
        """Every active rule defined for *organization_id*."""
        return await self._rules.list_for_org(organization_id)

    async def list_for_profile(self, profile_id: UUID) -> list[DiscoveryRule]:
        """Every active rule associated with *profile_id*, highest priority first."""
        return await self._rules.list_for_profile(profile_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID | None,
        rule_type: RuleType,
        field: str,
        operator: str,
        value: Any,
        priority: int = 0,
    ) -> DiscoveryRule:
        """Create a new rule."""
        return await self._rules.create(
            DiscoveryRule(
                organization_id=organization_id,
                profile_id=profile_id,
                rule_type=rule_type,
                field=field,
                operator=operator,
                value=value,
                priority=priority,
            )
        )

    async def delete(self, rule_id: UUID) -> None:
        """Delete a rule.

        Raises:
            NotFoundError: If no such rule exists.
        """
        await self._rules.delete(rule_id)


__all__ = ["DiscoveryRuleService", "matches_rule"]
