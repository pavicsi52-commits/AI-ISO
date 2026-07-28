"""Alert rule evaluation ("RULE ENGINE" "Support").

Evaluates an :class:`~app.models.alert_rule.AlertRule`'s own
:class:`~app.models.alert_condition.AlertCondition` rows against an
incoming event payload, combining them per the rule's own
``boolean_operator`` ("Boolean Logic"/"Composite Rules"). Reuses
``shared_core.workflow.expressions.evaluate_condition`` (Jinja2
``SandboxedEnvironment``) -- the same proven-safe evaluator every prior
AI-IOS rule engine established -- rather than ``eval()`` or a
hand-rolled AST walker, since a condition expression may come from a
user-authored rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shared_core.workflow.exceptions import ExpressionEvaluationError
from shared_core.workflow.expressions import evaluate_condition

from app.models.alert_condition import AlertCondition
from app.models.alert_rule import AlertRule
from app.models.enums import BooleanOperator


def evaluate_expression(expression: str, payload: dict[str, Any]) -> bool:
    """Evaluate one condition expression against *payload*.

    A malformed or erroring expression is treated as "did not match"
    (fail safe -- a broken rule must never be mistaken for a fired
    one, which would raise a false alert).
    """
    try:
        return evaluate_condition(expression, payload)
    except ExpressionEvaluationError:
        return False


def evaluate_rule(
    rule: AlertRule, conditions: Sequence[AlertCondition], payload: dict[str, Any]
) -> bool:
    """Return whether *rule* fires for *payload*.

    A rule with **no** conditions never fires. This mirrors
    ``services/validation-service``'s own already-established "an
    absent rule is never silently a pass" discipline, inverted for
    alerting's own opposite polarity: there, a check with no rules
    could not silently *pass*; here, a rule with no conditions must not
    silently *fire*. Either way an unconfigured rule never produces a
    confident verdict.
    """
    if not conditions:
        return False
    results = (evaluate_expression(condition.expression, payload) for condition in conditions)
    if rule.boolean_operator == BooleanOperator.OR:
        return any(results)
    return all(results)


__all__ = ["evaluate_expression", "evaluate_rule"]
