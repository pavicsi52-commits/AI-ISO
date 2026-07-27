"""The rule engine's own condition evaluation ("Conditional Checks"/
"Rule Chaining"). Built directly on
``shared_core.workflow.expressions.evaluate_condition`` -- the same
Jinja2-``SandboxedEnvironment``-backed evaluator
``shared_core.workflow``'s own conditional nodes already use -- rather
than a hand-rolled or ``eval``-based one, since a rule's own
``condition`` string may ultimately be authored by an organization
admin through the API, not just trusted source code.
"""

from __future__ import annotations

from typing import Any

from shared_core.workflow.exceptions import ExpressionEvaluationError
from shared_core.workflow.expressions import evaluate_condition

from app.models.enums import ValidationResultStatus
from app.models.validation_rule import ValidationRule


def evaluate_rule(rule: ValidationRule, collected_data: dict[str, Any]) -> ValidationResultStatus:
    """Evaluate *rule*'s own condition against *collected_data*.

    Returns *rule*'s own ``result_status`` if the condition matches,
    :attr:`~ValidationResultStatus.PASSED` if it doesn't, and
    :attr:`~ValidationResultStatus.UNKNOWN` if the condition itself
    fails to evaluate (e.g. it references a key ``collected_data``
    doesn't have) -- a broken rule is never silently treated as either
    a pass or a fail.
    """
    try:
        matched = evaluate_condition(rule.condition, collected_data)
    except ExpressionEvaluationError:
        return ValidationResultStatus.UNKNOWN
    return rule.result_status if matched else ValidationResultStatus.PASSED


def evaluate_rule_chain(
    rules: list[ValidationRule], collected_data: dict[str, Any]
) -> tuple[ValidationResultStatus, ValidationRule | None]:
    """Evaluate *rules* in priority order, returning the first non-passing
    outcome and the rule that produced it ("Rule Chaining").

    Returns :attr:`~ValidationResultStatus.PASSED` with no rule if every
    rule passes, or :attr:`~ValidationResultStatus.UNKNOWN` with no rule
    if *rules* is empty (an absent rule is never silently a pass).
    """
    if not rules:
        return ValidationResultStatus.UNKNOWN, None
    for rule in rules:
        status = evaluate_rule(rule, collected_data)
        if status != ValidationResultStatus.PASSED:
            return status, rule
    return ValidationResultStatus.PASSED, None


__all__ = ["evaluate_rule", "evaluate_rule_chain"]
