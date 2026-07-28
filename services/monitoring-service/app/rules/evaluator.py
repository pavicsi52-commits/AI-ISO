"""Evaluates a
:class:`~app.models.monitoring_rule.MonitoringRule`'s own ``condition``
against a metric's own recently collected data ("RULE ENGINE" "Metric
Rules"/"Composite Rules"/"Correlation Rules"). Reuses
``shared_core.workflow.expressions.evaluate_condition`` (Jinja2
sandboxed) -- the same proven-safe evaluator
``services/validation-service``'s own :mod:`app.rules.evaluator`
already established -- rather than a hand-rolled or ``eval()``-based one.
"""

from __future__ import annotations

from typing import Any

from shared_core.workflow.exceptions import ExpressionEvaluationError
from shared_core.workflow.expressions import evaluate_condition

from app.models.monitoring_rule import MonitoringRule


def evaluate_rule(rule: MonitoringRule, data: dict[str, Any]) -> bool:
    """Return whether *rule*'s own condition matches *data*.

    A malformed or erroring condition is treated as "did not match"
    (fail safe -- a broken rule must never be mistaken for a fired one).
    """
    try:
        return evaluate_condition(rule.condition, data)
    except ExpressionEvaluationError:
        return False


__all__ = ["evaluate_rule"]
