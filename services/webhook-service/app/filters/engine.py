"""Event-filtering rule evaluation (docs/057 "EVENT FILTERING").

A genuine gap -- no rule-matching primitive exists anywhere in
`shared_core` for this shape of problem (a small, caller-authored list
of field/operator/value conditions evaluated against an event's own
attributes). Built new, pure, and dependency-free.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.models.enums import FilterMatchMode

_OPERATORS = frozenset({"eq", "ne", "in", "not_in", "contains", "gt", "lt", "exists"})

_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda actual, expected: bool(actual == expected),
    "ne": lambda actual, expected: bool(actual != expected),
    "in": lambda actual, expected: expected is not None and actual in expected,
    "not_in": lambda actual, expected: expected is None or actual not in expected,
    "contains": lambda actual, expected: hasattr(actual, "__contains__") and expected in actual,
    "gt": lambda actual, expected: bool(actual > expected),
    "lt": lambda actual, expected: bool(actual < expected),
}
"""Every operator but ``exists``, which short-circuits before *expected* is ever compared."""


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
    return _COMPARATORS[operator](actual, expected)


def evaluate_rules(
    event_attributes: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
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
