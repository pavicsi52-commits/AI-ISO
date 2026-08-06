"""Event-filtering rule evaluation (docs/057 "EVENT FILTERING").

A genuine gap -- no rule-matching primitive exists anywhere in
`shared_core` for this shape of problem (a small, caller-authored list
of field/operator/value conditions evaluated against an event's own
attributes). Built new, pure, and dependency-free.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.enums import FilterMatchMode

_OPERATORS = frozenset({"eq", "ne", "in", "not_in", "contains", "gt", "lt", "exists"})


def _resolve_field(event_attributes: Mapping[str, Any], field: str) -> Any:
    """Resolve a dotted field path (e.g. ``"labels.team"``) against *event_attributes*."""
    current: Any = event_attributes
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def evaluate_rule(event_attributes: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Evaluate one ``{"field", "operator", "value"}`` rule against an event.

    Raises:
        ValueError: If ``rule["operator"]`` is not a recognised operator.
    """
    operator = rule.get("operator", "eq")
    if operator not in _OPERATORS:
        raise ValueError(f"Unrecognised filter operator: {operator!r}")
    field = rule.get("field", "")
    actual = _resolve_field(event_attributes, str(field))
    expected = rule.get("value")

    if operator == "exists":
        return actual is not None
    if actual is None:
        return False
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "in":
        return actual in expected if expected is not None else False
    if operator == "not_in":
        return actual not in expected if expected is not None else True
    if operator == "contains":
        return expected in actual if hasattr(actual, "__contains__") else False
    if operator == "gt":
        return bool(actual > expected)
    return bool(actual < expected)  # operator == "lt"


def evaluate_rules(
    event_attributes: Mapping[str, Any],
    rules: list[Mapping[str, Any]],
    *,
    match_mode: FilterMatchMode = FilterMatchMode.ALL,
) -> bool:
    """Evaluate every rule in *rules* against *event_attributes*.

    An empty rule list always matches -- a filter with no rules configured
    is a no-op pass-through, not a universal rejection.
    """
    if not rules:
        return True
    results = (evaluate_rule(event_attributes, rule) for rule in rules)
    return all(results) if match_mode == FilterMatchMode.ALL else any(results)


__all__ = ["evaluate_rule", "evaluate_rules"]
