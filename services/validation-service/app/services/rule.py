"""Rule catalog CRUD, backing the rule engine's own condition evaluation
(:mod:`app.rules.evaluator`).
"""

from __future__ import annotations

from uuid import UUID

from app.models.enums import ValidationResultStatus, ValidationSeverity
from app.models.validation_rule import ValidationRule
from app.repositories.validation_rule import ValidationRuleRepository


class ValidationRuleService:
    """Creates and reads validation rules."""

    def __init__(self, rules: ValidationRuleRepository) -> None:
        self._rules = rules

    async def get_by_id(self, rule_id: UUID) -> ValidationRule:
        """Return the rule identified by *rule_id*.

        Raises:
            NotFoundError: If no such rule exists.
        """
        return await self._rules.require_by_id(rule_id)

    async def list_for_check(self, check_id: UUID) -> list[ValidationRule]:
        """Every active rule for *check_id*, evaluation order."""
        return await self._rules.list_for_check(check_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        check_id: UUID,
        name: str,
        description: str | None,
        condition: str,
        result_status: ValidationResultStatus,
        severity: ValidationSeverity,
        weight: float,
        remediation_hint: str | None,
        priority: int,
    ) -> ValidationRule:
        """Create a new rule against a check's own collected data."""
        return await self._rules.create(
            ValidationRule(
                organization_id=organization_id,
                check_id=check_id,
                name=name,
                description=description,
                condition=condition,
                result_status=result_status,
                severity=severity,
                weight=weight,
                remediation_hint=remediation_hint,
                priority=priority,
            )
        )


__all__ = ["ValidationRuleService"]
