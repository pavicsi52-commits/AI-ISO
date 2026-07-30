"""Condition operators: how one attribute is compared to one value.

**There is no ``eval`` here, and there never will be.** A policy engine
whose expression language reaches Python evaluation is a remote code
execution endpoint wearing a governance hat -- policies are authored
through an API, stored in a database, and evaluated inside the process
that authorizes everything else on the platform. So "Expressions" and
"Custom Expressions" in docs/050 are implemented as this fixed operator
table over resolved attribute values, and a condition that names an
operator not in the table is a validation error at *authoring* time.

That is a deliberate trade. It costs expressiveness -- you cannot write
arbitrary arithmetic in a policy -- and buys the guarantee that no
stored string is ever executed. Nested boolean rules
(:mod:`app.rules.engine`) recover most of the expressiveness that a
governance policy actually needs.

**Every operator is total.** None raises for a type it did not expect;
a comparison that cannot be made returns ``False`` and says why. An
operator that raised would turn one malformed condition into a failed
evaluation, and a failed evaluation into either an outage or -- far
worse -- a fallback that grants.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.models.enums import RuleOperator

MAX_PATTERN_LENGTH = 512
"""Longest regular expression a condition may hold.

Bounded because a policy is caller-authored data that runs on the
authorization path. Python's ``re`` has no step limit, so a pattern like
``(a+)+$`` against a long value takes exponential time -- one stored
policy would stall every decision in the estate.
"""

_MAX_MATCH_INPUT = 4_096
"""Longest value a pattern operator will scan.

The second half of the catastrophic-backtracking defence: bounding the
pattern alone is not enough, because runtime grows with the *input* too.
Longer values do not error -- they simply do not match, which is the
safe direction for a comparison whose failure mode is a grant.
"""

_DAY_NAMES: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """The outcome of one comparison, with why it came out that way."""

    matched: bool
    detail: str = ""

    def __bool__(self) -> bool:
        """Allow a result to be used directly in a boolean context."""
        return self.matched


def _as_sequence(value: Any) -> list[Any]:
    """Coerce a value into a list for membership comparisons.

    A bare string is wrapped rather than iterated: treating ``"prod"`` as
    ``["p", "r", "o", "d"]`` makes ``contains`` silently true for any
    single letter in it, which is the kind of wrong that reads as
    working.
    """
    if isinstance(value, str | bytes):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    if isinstance(value, set | frozenset):
        return sorted(value, key=repr)
    return [value]


def _as_number(value: Any) -> float | None:
    """Coerce to a float, or ``None`` if it is not numeric.

    ``bool`` is refused explicitly: it is a subclass of ``int`` in
    Python, so ``True > 0`` is legal and meaningless in a policy.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_time(value: Any) -> time | None:
    """Coerce to a wall-clock time, or ``None``."""
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.timetz()
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    """Coerce to an aware datetime, or ``None``."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a condition's regular expression, bounded.

    Raises:
        ValidationError: If the pattern is too long or not valid. Raised
            at *authoring* time, so a policy carrying an unusable pattern
            is refused when someone writes it rather than failing every
            decision it later touches.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValidationError(
            f"A condition pattern may be at most {MAX_PATTERN_LENGTH} characters, "
            f"got {len(pattern)}."
        )
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValidationError(f"Not a valid regular expression: {exc}") from exc


def _match(actual: Any, expected: Any, *, negate: bool) -> ComparisonResult:
    """Regular-expression match, bounded on both pattern and input."""
    if not isinstance(actual, str):
        return ComparisonResult(negate, f"{type(actual).__name__} is not text")
    if len(actual) > _MAX_MATCH_INPUT:
        return ComparisonResult(
            False, f"value exceeds the {_MAX_MATCH_INPUT}-character matching limit"
        )
    try:
        pattern = compile_pattern(str(expected))
    except ValidationError as exc:
        return ComparisonResult(False, str(exc))
    found = pattern.search(actual) is not None
    return ComparisonResult(found != negate)


def _between(actual: Any, expected: Any) -> ComparisonResult:
    """Inclusive range check over two bounds."""
    bounds = _as_sequence(expected)
    expected_bounds = 2
    if len(bounds) != expected_bounds:
        return ComparisonResult(False, "'between' needs exactly two bounds")
    value, low, high = (_as_number(one) for one in (actual, bounds[0], bounds[1]))
    if value is None or low is None or high is None:
        return ComparisonResult(False, "'between' needs numeric values")
    if low > high:
        low, high = high, low
    return ComparisonResult(low <= value <= high)


def _time_between(actual: Any, expected: Any) -> ComparisonResult:
    """Wall-clock window, correct across midnight.

    A maintenance window from 22:00 to 06:00 is the normal case, not the
    exotic one, so the wrapped comparison is the point of this operator
    rather than an edge case bolted on.
    """
    bounds = _as_sequence(expected)
    expected_bounds = 2
    if len(bounds) != expected_bounds:
        return ComparisonResult(False, "'time_between' needs exactly two bounds")
    moment = _as_time(actual)
    start, end = _as_time(bounds[0]), _as_time(bounds[1])
    if moment is None or start is None or end is None:
        return ComparisonResult(False, "'time_between' needs times")
    naive = time(moment.hour, moment.minute, moment.second)
    if start <= end:
        return ComparisonResult(start <= naive <= end)
    return ComparisonResult(naive >= start or naive <= end)


def _day_of_week_in(actual: Any, expected: Any) -> ComparisonResult:
    """Day-of-week membership, by name or by ISO number."""
    moment = _as_datetime(actual)
    if moment is None:
        return ComparisonResult(False, "'day_of_week_in' needs a datetime")
    wanted: set[int] = set()
    for one in _as_sequence(expected):
        if isinstance(one, str) and one.strip().lower() in _DAY_NAMES:
            wanted.add(_DAY_NAMES[one.strip().lower()])
            continue
        number = _as_number(one)
        if number is not None:
            wanted.add(int(number) % 7)
    if not wanted:
        return ComparisonResult(False, "'day_of_week_in' named no recognisable days")
    return ComparisonResult(moment.weekday() in wanted)


def _cidr_contains(actual: Any, expected: Any) -> ComparisonResult:
    """Whether an address falls inside any of the given networks.

    Parsed rather than string-prefixed. ``10.0.0.1`` starts with
    ``10.0.0.`` and so does ``10.0.0.100``, but a prefix test also
    matches ``10.0.0.1`` against network ``10.0.0.10/32`` -- an
    IP-allow-list built on ``startswith`` grants addresses nobody
    intended.
    """
    try:
        address = ipaddress.ip_address(str(actual))
    except ValueError:
        return ComparisonResult(False, f"{actual!r} is not an IP address")
    for one in _as_sequence(expected):
        try:
            network = ipaddress.ip_network(str(one), strict=False)
        except ValueError:
            continue
        if address.version == network.version and address in network:
            return ComparisonResult(True)
    return ComparisonResult(False)


def _compare_numeric(
    actual: Any, expected: Any, operation: Callable[[float, float], bool], name: str
) -> ComparisonResult:
    """Ordered comparison, refusing anything not genuinely numeric."""
    left, right = _as_number(actual), _as_number(expected)
    if left is None or right is None:
        return ComparisonResult(False, f"{name!r} needs numeric values")
    return ComparisonResult(operation(left, right))


_MISSING = object()
"""Sentinel for an attribute that was not present at all.

Distinct from ``None``, which is a *value* a resolved attribute may
legitimately hold. Collapsing the two makes ``exists`` answer wrongly
for any attribute explicitly set to null.
"""


def evaluate(operator: RuleOperator, actual: Any, expected: Any = None) -> ComparisonResult:
    """Apply one operator, totally.

    Never raises. A comparison that cannot be made returns
    ``ComparisonResult(False, reason)``, because the alternative -- an
    exception escaping into the evaluator -- turns one malformed
    condition into a failed decision, and a failed decision into either
    an outage or a fallback that grants.
    """
    handler = _OPERATORS.get(operator)
    if handler is None:  # pragma: no cover - unreachable while the table is complete
        return ComparisonResult(False, f"unsupported operator {operator!r}")
    try:
        return handler(actual, expected)
    except Exception as exc:  # pragma: no cover - operators are total by construction
        return ComparisonResult(False, f"comparison failed: {exc}")


_OPERATORS: dict[RuleOperator, Callable[[Any, Any], ComparisonResult]] = {
    RuleOperator.EQUALS: lambda a, e: ComparisonResult(a == e),
    RuleOperator.NOT_EQUALS: lambda a, e: ComparisonResult(a != e),
    RuleOperator.IN: lambda a, e: ComparisonResult(a in _as_sequence(e)),
    RuleOperator.NOT_IN: lambda a, e: ComparisonResult(a not in _as_sequence(e)),
    RuleOperator.CONTAINS: lambda a, e: ComparisonResult(e in _as_sequence(a)),
    RuleOperator.NOT_CONTAINS: lambda a, e: ComparisonResult(e not in _as_sequence(a)),
    RuleOperator.STARTS_WITH: lambda a, e: ComparisonResult(
        isinstance(a, str) and a.startswith(str(e))
    ),
    RuleOperator.ENDS_WITH: lambda a, e: ComparisonResult(
        isinstance(a, str) and a.endswith(str(e))
    ),
    RuleOperator.MATCHES: lambda a, e: _match(a, e, negate=False),
    RuleOperator.NOT_MATCHES: lambda a, e: _match(a, e, negate=True),
    RuleOperator.GREATER_THAN: lambda a, e: _compare_numeric(
        a, e, lambda x, y: x > y, "greater_than"
    ),
    RuleOperator.GREATER_OR_EQUAL: lambda a, e: _compare_numeric(
        a, e, lambda x, y: x >= y, "greater_or_equal"
    ),
    RuleOperator.LESS_THAN: lambda a, e: _compare_numeric(a, e, lambda x, y: x < y, "less_than"),
    RuleOperator.LESS_OR_EQUAL: lambda a, e: _compare_numeric(
        a, e, lambda x, y: x <= y, "less_or_equal"
    ),
    RuleOperator.BETWEEN: _between,
    RuleOperator.EXISTS: lambda a, _e: ComparisonResult(a is not _MISSING and a is not None),
    RuleOperator.NOT_EXISTS: lambda a, _e: ComparisonResult(a is _MISSING or a is None),
    RuleOperator.IS_EMPTY: lambda a, _e: ComparisonResult(
        a is _MISSING or a is None or (hasattr(a, "__len__") and len(a) == 0)
    ),
    RuleOperator.IS_NOT_EMPTY: lambda a, _e: ComparisonResult(
        a is not _MISSING and a is not None and (not hasattr(a, "__len__") or len(a) > 0)
    ),
    RuleOperator.SUBSET_OF: lambda a, e: ComparisonResult(
        set(map(repr, _as_sequence(a))) <= set(map(repr, _as_sequence(e)))
    ),
    RuleOperator.SUPERSET_OF: lambda a, e: ComparisonResult(
        set(map(repr, _as_sequence(a))) >= set(map(repr, _as_sequence(e)))
    ),
    RuleOperator.INTERSECTS: lambda a, e: ComparisonResult(
        bool(set(map(repr, _as_sequence(a))) & set(map(repr, _as_sequence(e))))
    ),
    RuleOperator.TIME_BETWEEN: _time_between,
    RuleOperator.DAY_OF_WEEK_IN: _day_of_week_in,
    RuleOperator.CIDR_CONTAINS: _cidr_contains,
}
"""Every operator, as a pure function.

A table rather than a chain of branches, so a member added to
:class:`~app.models.enums.RuleOperator` without an implementation is
caught by the completeness test instead of silently never matching.
"""

OPERATORS_REQUIRING_VALUE: frozenset[RuleOperator] = frozenset(
    set(RuleOperator)
    - {
        RuleOperator.EXISTS,
        RuleOperator.NOT_EXISTS,
        RuleOperator.IS_EMPTY,
        RuleOperator.IS_NOT_EMPTY,
    }
)
"""Operators that are meaningless without a comparison value.

Checked when a condition is authored. ``equals`` with nothing to equal
is not a strict condition -- it is one that quietly matches attributes
that happen to be null.
"""


__all__ = [
    "MAX_PATTERN_LENGTH",
    "OPERATORS_REQUIRING_VALUE",
    "ComparisonResult",
    "compile_pattern",
    "evaluate",
]
