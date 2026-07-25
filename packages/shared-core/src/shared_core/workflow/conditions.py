"""Condition and rules evaluation.

Per docs/028_Enterprise_Workflow_SDK.md.txt "CONDITIONS": If, Else,
Switch, Match, Expression, Rules Engine, Variable Evaluation. Built on
:func:`shared_core.workflow.expressions.evaluate_condition`/
:func:`~shared_core.workflow.expressions.evaluate_expression` -- this
module only adds the "if/else", "switch/match", and "ordered rules"
shapes on top of that one evaluation primitive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shared_core.workflow.expressions import evaluate_condition, evaluate_expression


def evaluate_if_else(condition: str, variables: dict[str, Any]) -> bool:
    """Evaluate an ``If``/``Else`` branch condition ("If"/"Else")."""
    return evaluate_condition(condition, variables)


def evaluate_switch(
    cases: Mapping[str, str], variables: dict[str, Any], *, default: str | None = None
) -> str | None:
    """Evaluate each case's condition in order, returning the first matching case's key ("Switch").

    Returns *default* (``None`` unless given) if no case matches.
    """
    for case_key, case_condition in cases.items():
        if evaluate_condition(case_condition, variables):
            return case_key
    return default


def evaluate_match(
    value_expression: str,
    cases: Mapping[Any, str],
    variables: dict[str, Any],
    *,
    default: str | None = None,
) -> str | None:
    """Evaluate *value_expression* and return the case key whose value it matches ("Match")."""
    value = evaluate_expression(value_expression, variables)
    return cases.get(value, default)


@dataclass(frozen=True, slots=True)
class Rule:
    """One ordered rule in an :func:`evaluate_rules` chain ("Rules Engine")."""

    condition: str
    result: str


def evaluate_rules(
    rules: list[Rule], variables: dict[str, Any], *, default: str | None = None
) -> str | None:
    """Evaluate *rules* in order, returning the first matching rule's result ("Rules Engine").

    Returns *default* if no rule matches.
    """
    for rule in rules:
        if evaluate_condition(rule.condition, variables):
            return rule.result
    return default


__all__ = ["Rule", "evaluate_if_else", "evaluate_match", "evaluate_rules", "evaluate_switch"]
