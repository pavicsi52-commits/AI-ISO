"""Event routing (docs/058 "EVENT ROUTING").

A genuine gap -- no rule-matching-plus-fan-out primitive exists in
`shared_core` for this shape of problem. Pure and dependency-free,
mirroring the same filter-then-match structure webhook-service's own
`app/filters/engine.py` established for a different domain (endpoint
subscriptions rather than routing destinations) -- no code is shared
between the two services (no cross-service imports exist anywhere in
this monorepo), only the pattern.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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


def _resolve_path(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        current = current.get(part) if isinstance(current, Mapping) else None
    return current


def evaluate_rule(event_attributes: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Evaluate one ``{"field", "operator", "value"}`` rule against an event.

    Raises:
        ValueError: If ``rule["operator"]`` is not a recognised operator.
    """
    operator = rule.get("operator", "eq")
    if operator not in _OPERATORS:
        raise ValueError(f"Unrecognised routing operator: {operator!r}")
    actual = _resolve_path(event_attributes, str(rule.get("field", "")))
    expected = rule.get("value")
    if operator == "exists":
        return actual is not None
    if actual is None:
        return False
    return _COMPARATORS[operator](actual, expected)


def matches_route(event_attributes: Mapping[str, Any], route: Mapping[str, Any]) -> bool:
    """Whether every one of *route*'s own ``"filter_rules"`` passes for this event.

    A route with no filter rules always matches -- an unfiltered
    destination is a pass-through, not a universal rejection, matching
    the same "empty rule list always matches" precedent every other
    filter engine in this platform already establishes.
    """
    rules: Sequence[Mapping[str, Any]] = route.get("filter_rules", [])
    return all(evaluate_rule(event_attributes, rule) for rule in rules)


def enrich_payload(payload: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    """Merge *route*'s own ``"enrichment"`` static fields into *payload*."""
    enriched = dict(payload)
    for key, value in route.get("enrichment", {}).items():
        enriched.setdefault(key, value)
    return enriched


@dataclass(frozen=True, slots=True)
class RoutedDestination:
    """One route this event actually matched, with its own enriched payload."""

    destination_kind: str
    destination_config: dict[str, Any]
    payload: dict[str, Any]


def resolve_routes(
    event_attributes: Mapping[str, Any],
    payload: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
) -> list[RoutedDestination]:
    """Every route in *routes* whose own filter matches this event, enriched and ready to send."""
    return [
        RoutedDestination(
            destination_kind=str(route.get("destination_kind", "")),
            destination_config=dict(route.get("destination_config", {})),
            payload=enrich_payload(payload, route),
        )
        for route in routes
        if matches_route(event_attributes, route)
    ]


__all__ = [
    "RoutedDestination",
    "enrich_payload",
    "evaluate_rule",
    "matches_route",
    "resolve_routes",
]
