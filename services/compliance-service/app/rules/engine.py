"""Evaluating an automatable control against collected evidence.

A control's ``rule`` is data, never code. It is authored by compliance
staff, stored in the database, and evaluated here by a dispatch table --
so a control definition can be edited by somebody who should not be able
to execute arbitrary Python on the assessment worker, which is everyone.

The module is **pure**: no database, no network, no clock it was not
handed. That is what makes an assessment's verdict reproducible, and
reproducibility is not a nicety here -- an auditor is entitled to ask
why a control failed in March, and the answer has to be derivable from
the evidence that was stored, not from whatever the estate looks like
today.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from shared_core.exceptions.validation import ValidationError

MAX_RULE_DEPTH = 8
"""How deeply a control's rule may nest.

Bounded because the evaluator recurses and a hand-edited JSON blob is
the sort of thing that arrives 4,000 levels deep exactly once, taking
the assessment worker's stack with it.
"""

MAX_CHECKS_PER_RULE = 100
MAX_PATH_DEPTH = 8
BETWEEN_BOUNDS = 2
"""``between`` takes exactly a low and a high; anything else is malformed."""

MAX_PATTERN_LENGTH = 512
_MAX_MATCH_INPUT = 4_096
"""Ceilings on the regex operators.

A control author is a user like any other, and a catastrophic pattern in
a compliance rule would stall an assessment that is meant to run
unattended overnight.
"""


class _Missing:
    """The absence of a value, distinct from a stored ``None``.

    A control checking ``tls.min_version >= 1.2`` must not pass because
    the collector never reported ``tls`` at all. Conflating "absent" with
    "null" is how a compliance tool comes to certify hosts it never
    successfully inspected.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


MISSING = _Missing()


class CheckOperator(StrEnum):
    """The comparisons a control rule may make."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"
    NOT_MATCHES = "not_matches"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    SUBSET_OF = "subset_of"
    SUPERSET_OF = "superset_of"
    INTERSECTS = "intersects"
    CIDR_CONTAINS = "cidr_contains"
    OLDER_THAN_DAYS = "older_than_days"
    NEWER_THAN_DAYS = "newer_than_days"
    COUNT_EQUALS = "count_equals"
    COUNT_AT_LEAST = "count_at_least"
    COUNT_AT_MOST = "count_at_most"


class LogicalOperator(StrEnum):
    """How a rule combines its checks and children."""

    ALL = "all"
    ANY = "any"
    NONE = "none"


@dataclass(slots=True)
class Check:
    """One comparison against a path in the evidence payload."""

    path: str
    operator: CheckOperator
    value: Any = None
    negate: bool = False
    description: str = ""


@dataclass(slots=True)
class Rule:
    """A logical combination of checks and nested rules."""

    name: str = "rule"
    logical_operator: LogicalOperator = LogicalOperator.ALL
    checks: list[Check] = field(default_factory=list)
    children: list[Rule] = field(default_factory=list)
    negate: bool = False
    description: str = ""


@dataclass(slots=True)
class CheckOutcome:
    """What one check decided, and why."""

    path: str
    operator: str
    passed: bool
    expected: Any
    observed: Any

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form, safe for an evidence payload."""
        return {
            "path": self.path,
            "operator": self.operator,
            "passed": self.passed,
            "expected": _plain(self.expected),
            "observed": _plain(self.observed),
        }


@dataclass(slots=True)
class RuleOutcome:
    """What a whole rule decided, with every check that contributed.

    The check list is the point. A control that merely reports "failed"
    produces a finding nobody can act on; a control that reports *which
    comparison* failed, against what was expected and what was actually
    observed, produces one somebody can fix without re-running anything.
    """

    passed: bool
    rule_name: str
    checks: list[CheckOutcome] = field(default_factory=list)
    children: list[RuleOutcome] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "rule": self.rule_name,
            "passed": self.passed,
            "checks": [one.as_dict() for one in self.checks],
            "children": [one.as_dict() for one in self.children],
        }

    def failures(self) -> list[CheckOutcome]:
        """Every failing check, depth-first, for the finding's reason."""
        found = [one for one in self.checks if not one.passed]
        for child in self.children:
            found.extend(child.failures())
        return found


def _plain(value: Any) -> Any:
    """Render a value in a form ``json.dumps`` will accept.

    Every check outcome is stored on a result row, so a value json
    refuses here is a 500 at write time -- after the assessment has
    already done all its work.
    """
    if isinstance(value, _Missing):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(_plain(one) for one in value)
    if isinstance(value, list):
        return [_plain(one) for one in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


# ---- path resolution --------------------------------------------------


def resolve(payload: dict[str, Any], path: str) -> Any:
    """Read a dotted path out of an evidence payload.

    Returns :data:`MISSING` rather than ``None`` when any segment is
    absent, so an operator can tell "the collector reported null" from
    "the collector never reported this".

    Supports numeric segments for lists, so ``users.0.name`` works on
    the shape collectors actually produce.
    """
    current: Any = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not segment.isdigit():
                return MISSING
            index = int(segment)
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def validate_path(path: str) -> None:
    """Refuse a path that is empty, too deep, or malformed.

    Raises:
        ValidationError: If the path cannot address anything.
    """
    if not path or not path.strip():
        raise ValidationError("A check needs an attribute path.")
    segments = path.split(".")
    if len(segments) > MAX_PATH_DEPTH:
        raise ValidationError(
            f"Path {path!r} is {len(segments)} segments deep; the maximum is {MAX_PATH_DEPTH}."
        )
    if any(not segment for segment in segments):
        raise ValidationError(f"Path {path!r} has an empty segment.")


# ---- operators --------------------------------------------------------
#
# Every operator is an ordinary function. Nothing from a stored control
# is ever executed, compiled, or passed to eval.


def _as_number(value: Any) -> float | None:
    """Coerce to a float, or ``None`` if it is not numeric.

    Booleans are refused deliberately: Python treats ``True`` as ``1``,
    so a control asserting ``replicas >= 1`` would otherwise be satisfied
    by a collector that reported ``replicas: true``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    """Coerce to an aware datetime, or ``None``."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _as_sequence(value: Any) -> list[Any] | None:
    """Coerce to a list, treating a string as a scalar rather than chars."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return None


def _compile(pattern: Any) -> re.Pattern[str] | None:
    """Compile a bounded pattern, or ``None`` if it is unusable."""
    if not isinstance(pattern, str) or not pattern:
        return None
    if len(pattern) > MAX_PATTERN_LENGTH:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        return None


def _op_equals(observed: Any, expected: Any) -> bool:
    return observed is not MISSING and observed == expected


def _op_in(observed: Any, expected: Any) -> bool:
    items = _as_sequence(expected)
    return items is not None and observed is not MISSING and observed in items


def _op_contains(observed: Any, expected: Any) -> bool:
    if observed is MISSING:
        return False
    if isinstance(observed, str):
        return isinstance(expected, str) and expected in observed
    items = _as_sequence(observed)
    return items is not None and expected in items


def _op_starts_with(observed: Any, expected: Any) -> bool:
    return isinstance(observed, str) and isinstance(expected, str) and observed.startswith(expected)


def _op_ends_with(observed: Any, expected: Any) -> bool:
    return isinstance(observed, str) and isinstance(expected, str) and observed.endswith(expected)


def _op_matches(observed: Any, expected: Any) -> bool:
    pattern = _compile(expected)
    if pattern is None or not isinstance(observed, str):
        return False
    return pattern.search(observed[:_MAX_MATCH_INPUT]) is not None


def _op_greater_than(observed: Any, expected: Any) -> bool:
    left, right = _as_number(observed), _as_number(expected)
    return left is not None and right is not None and left > right


def _op_greater_or_equal(observed: Any, expected: Any) -> bool:
    left, right = _as_number(observed), _as_number(expected)
    return left is not None and right is not None and left >= right


def _op_less_than(observed: Any, expected: Any) -> bool:
    left, right = _as_number(observed), _as_number(expected)
    return left is not None and right is not None and left < right


def _op_less_or_equal(observed: Any, expected: Any) -> bool:
    left, right = _as_number(observed), _as_number(expected)
    return left is not None and right is not None and left <= right


def _op_between(observed: Any, expected: Any) -> bool:
    bounds = _as_sequence(expected)
    if bounds is None or len(bounds) != BETWEEN_BOUNDS:
        return False
    value = _as_number(observed)
    low, high = _as_number(bounds[0]), _as_number(bounds[1])
    if value is None or low is None or high is None:
        return False
    return low <= value <= high


def _op_exists(observed: Any, _expected: Any) -> bool:
    return observed is not MISSING


def _op_is_empty(observed: Any, _expected: Any) -> bool:
    if observed is MISSING or observed is None:
        return True
    if isinstance(observed, (str, list, tuple, set, frozenset, dict)):
        return len(observed) == 0
    return False


def _op_is_true(observed: Any, _expected: Any) -> bool:
    return observed is True


def _op_is_false(observed: Any, _expected: Any) -> bool:
    return observed is False


def _op_subset_of(observed: Any, expected: Any) -> bool:
    left, right = _as_sequence(observed), _as_sequence(expected)
    return left is not None and right is not None and set(left) <= set(right)


def _op_superset_of(observed: Any, expected: Any) -> bool:
    left, right = _as_sequence(observed), _as_sequence(expected)
    return left is not None and right is not None and set(left) >= set(right)


def _op_intersects(observed: Any, expected: Any) -> bool:
    left, right = _as_sequence(observed), _as_sequence(expected)
    return left is not None and right is not None and bool(set(left) & set(right))


def _op_cidr_contains(observed: Any, expected: Any) -> bool:
    """Whether *observed* is an address inside the network *expected*."""
    if not isinstance(observed, str) or not isinstance(expected, str):
        return False
    try:
        return ipaddress.ip_address(observed.strip()) in ipaddress.ip_network(
            expected.strip(), strict=False
        )
    except ValueError:
        return False


def _op_count_equals(observed: Any, expected: Any) -> bool:
    items = _as_sequence(observed)
    count = _as_number(expected)
    return items is not None and count is not None and len(items) == int(count)


def _op_count_at_least(observed: Any, expected: Any) -> bool:
    items = _as_sequence(observed)
    count = _as_number(expected)
    return items is not None and count is not None and len(items) >= int(count)


def _op_count_at_most(observed: Any, expected: Any) -> bool:
    items = _as_sequence(observed)
    count = _as_number(expected)
    return items is not None and count is not None and len(items) <= int(count)


_OPERATORS: dict[CheckOperator, Callable[[Any, Any], bool]] = {
    CheckOperator.EQUALS: _op_equals,
    CheckOperator.NOT_EQUALS: lambda o, e: not _op_equals(o, e),
    CheckOperator.IN: _op_in,
    CheckOperator.NOT_IN: lambda o, e: not _op_in(o, e),
    CheckOperator.CONTAINS: _op_contains,
    CheckOperator.NOT_CONTAINS: lambda o, e: not _op_contains(o, e),
    CheckOperator.STARTS_WITH: _op_starts_with,
    CheckOperator.ENDS_WITH: _op_ends_with,
    CheckOperator.MATCHES: _op_matches,
    CheckOperator.NOT_MATCHES: lambda o, e: not _op_matches(o, e),
    CheckOperator.GREATER_THAN: _op_greater_than,
    CheckOperator.GREATER_OR_EQUAL: _op_greater_or_equal,
    CheckOperator.LESS_THAN: _op_less_than,
    CheckOperator.LESS_OR_EQUAL: _op_less_or_equal,
    CheckOperator.BETWEEN: _op_between,
    CheckOperator.EXISTS: _op_exists,
    CheckOperator.NOT_EXISTS: lambda o, e: not _op_exists(o, e),
    CheckOperator.IS_EMPTY: _op_is_empty,
    CheckOperator.IS_NOT_EMPTY: lambda o, e: not _op_is_empty(o, e),
    CheckOperator.IS_TRUE: _op_is_true,
    CheckOperator.IS_FALSE: _op_is_false,
    CheckOperator.SUBSET_OF: _op_subset_of,
    CheckOperator.SUPERSET_OF: _op_superset_of,
    CheckOperator.INTERSECTS: _op_intersects,
    CheckOperator.CIDR_CONTAINS: _op_cidr_contains,
    CheckOperator.COUNT_EQUALS: _op_count_equals,
    CheckOperator.COUNT_AT_LEAST: _op_count_at_least,
    CheckOperator.COUNT_AT_MOST: _op_count_at_most,
}

_TIME_OPERATORS = frozenset({CheckOperator.OLDER_THAN_DAYS, CheckOperator.NEWER_THAN_DAYS})


def _evaluate_time(check: Check, observed: Any, now: datetime) -> bool:
    """Age comparisons, which need the assessment's reference moment.

    Dispatched separately from :data:`_OPERATORS` because these are the
    only two operators that need more than the observed and expected
    values. ``now`` is *passed in* rather than read here: a function that
    calls ``datetime.now`` is not pure, and an assessment nobody can
    reproduce is an assessment nobody can defend to an auditor asking
    why a control failed last March.
    """
    moment = _as_datetime(observed)
    days = _as_number(check.value)
    if moment is None or days is None:
        return False
    if moment.tzinfo is None or now.tzinfo is None:
        return False
    age_days = (now - moment).total_seconds() / 86_400.0
    if check.operator is CheckOperator.OLDER_THAN_DAYS:
        return age_days > days
    return age_days <= days


def evaluate_check(check: Check, payload: dict[str, Any], *, now: datetime) -> CheckOutcome:
    """Decide one check against one evidence payload."""
    observed = resolve(payload, check.path)
    if check.operator in _TIME_OPERATORS:
        passed = _evaluate_time(check, observed, now)
    else:
        passed = _OPERATORS[check.operator](observed, check.value)
    if check.negate:
        passed = not passed
    return CheckOutcome(
        path=check.path,
        operator=str(check.operator),
        passed=passed,
        expected=check.value,
        observed=observed,
    )


def evaluate_rule(rule: Rule, payload: dict[str, Any], *, now: datetime) -> RuleOutcome:
    """Decide a whole rule tree against one evidence payload.

    An ``ALL`` rule with no checks and no children passes -- vacuously
    true, and the only consistent answer -- which is exactly why
    :func:`validate_rule` refuses to let one be *saved*. A control that
    silently passes everything is the most dangerous thing this service
    could produce, and the place to stop it is authoring time, where a
    person is present to be told.
    """
    checks = [evaluate_check(one, payload, now=now) for one in rule.checks]
    children = [evaluate_rule(one, payload, now=now) for one in rule.children]
    verdicts = [one.passed for one in checks] + [one.passed for one in children]

    if rule.logical_operator is LogicalOperator.ALL:
        passed = all(verdicts)
    elif rule.logical_operator is LogicalOperator.ANY:
        passed = any(verdicts) if verdicts else False
    else:
        passed = not any(verdicts)

    if rule.negate:
        passed = not passed
    return RuleOutcome(passed=passed, rule_name=rule.name, checks=checks, children=children)


# ---- authoring --------------------------------------------------------


def validate_rule(rule: Rule, *, depth: int = 0) -> None:
    """Refuse a rule that cannot be evaluated meaningfully.

    Raises:
        ValidationError: If the rule is too deep, too wide, empty, or
            names a path that cannot address anything.
    """
    if depth > MAX_RULE_DEPTH:
        raise ValidationError(f"Rule {rule.name!r} nests deeper than {MAX_RULE_DEPTH} levels.")
    if len(rule.checks) > MAX_CHECKS_PER_RULE:
        raise ValidationError(
            f"Rule {rule.name!r} has {len(rule.checks)} checks; the maximum is "
            f"{MAX_CHECKS_PER_RULE}."
        )
    if not rule.checks and not rule.children:
        raise ValidationError(
            f"Rule {rule.name!r} has no checks and no children, so it would pass "
            "everything. A control that passes unconditionally certifies an estate "
            "nobody looked at."
        )
    for check in rule.checks:
        validate_path(check.path)
    for child in rule.children:
        validate_rule(child, depth=depth + 1)


def rule_from_dict(data: dict[str, Any], *, name: str = "rule", depth: int = 0) -> Rule:
    """Rebuild a :class:`Rule` from its stored JSON form.

    Raises:
        ValidationError: If the stored shape names an operator or
            structure that no longer exists -- which happens when a
            control outlives an enum member, and must fail loudly rather
            than evaluate as something adjacent.
    """
    if depth > MAX_RULE_DEPTH:
        raise ValidationError(f"Stored rule {name!r} nests deeper than {MAX_RULE_DEPTH} levels.")
    if not isinstance(data, dict):
        raise ValidationError(f"Stored rule {name!r} is not an object.")

    try:
        logical = LogicalOperator(str(data.get("logical_operator", LogicalOperator.ALL)))
    except ValueError as exc:
        raise ValidationError(f"Stored rule {name!r} names an unknown combinator: {exc}") from exc

    checks: list[Check] = []
    for raw in data.get("checks", []) or []:
        if not isinstance(raw, dict):
            raise ValidationError(f"Stored rule {name!r} has a check that is not an object.")
        try:
            operator = CheckOperator(str(raw.get("operator", "")))
        except ValueError as exc:
            raise ValidationError(
                f"Check on {raw.get('path')!r} names an unknown operator: {exc}"
            ) from exc
        checks.append(
            Check(
                path=str(raw.get("path", "")),
                operator=operator,
                value=raw.get("value"),
                negate=bool(raw.get("negate", False)),
                description=str(raw.get("description") or ""),
            )
        )

    children = [
        rule_from_dict(raw, name=str(raw.get("name", f"{name}.{index}")), depth=depth + 1)
        for index, raw in enumerate(data.get("children", []) or [])
        if isinstance(raw, dict)
    ]

    return Rule(
        name=str(data.get("name") or name),
        logical_operator=logical,
        checks=checks,
        children=children,
        negate=bool(data.get("negate", False)),
        description=str(data.get("description") or ""),
    )


def rule_to_dict(rule: Rule) -> dict[str, Any]:
    """Render a :class:`Rule` to its stored JSON form."""
    return {
        "name": rule.name,
        "logical_operator": str(rule.logical_operator),
        "negate": rule.negate,
        "description": rule.description,
        "checks": [
            {
                "path": one.path,
                "operator": str(one.operator),
                "value": _plain(one.value),
                "negate": one.negate,
                "description": one.description,
            }
            for one in rule.checks
        ],
        "children": [rule_to_dict(one) for one in rule.children],
    }


def referenced_paths(rule: Rule) -> list[str]:
    """Every evidence path a rule reads, deduplicated and sorted.

    What lets a collector be asked for exactly what a control needs
    rather than for everything -- the difference between an assessment
    that scales with the estate and one that scales with the catalogue
    times the estate.
    """
    found: set[str] = {one.path for one in rule.checks}
    for child in rule.children:
        found.update(referenced_paths(child))
    return sorted(found)


def describe_failures(outcome: RuleOutcome, *, limit: int = 5) -> str:
    """A human sentence naming why a control failed.

    Truncated, because a control failing on 400 paths produces a reason
    nobody reads. The full detail stays in the stored outcome.
    """
    failures = outcome.failures()
    if not failures:
        return "All checks passed."
    shown: Sequence[CheckOutcome] = failures[:limit]
    parts = [
        f"{one.path} {one.operator} {_plain(one.expected)!r} but observed {_plain(one.observed)!r}"
        for one in shown
    ]
    sentence = "; ".join(parts)
    if len(failures) > limit:
        sentence += f"; and {len(failures) - limit} more"
    return sentence + "."


__all__ = [
    "BETWEEN_BOUNDS",
    "MAX_CHECKS_PER_RULE",
    "MAX_PATH_DEPTH",
    "MAX_PATTERN_LENGTH",
    "MAX_RULE_DEPTH",
    "MISSING",
    "Check",
    "CheckOperator",
    "CheckOutcome",
    "LogicalOperator",
    "Rule",
    "RuleOutcome",
    "describe_failures",
    "evaluate_check",
    "evaluate_rule",
    "referenced_paths",
    "resolve",
    "rule_from_dict",
    "rule_to_dict",
    "validate_path",
    "validate_rule",
]
