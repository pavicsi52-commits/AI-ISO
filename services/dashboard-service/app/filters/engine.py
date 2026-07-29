"""Row filtering ("FILTERING").

Filters are applied **in this service, over rows already fetched**,
rather than being pushed into each source service's query string. The
thirteen data sources docs/048 names do not share a filter grammar, so
one expression could not be translated to all of them faithfully.
Applying a single consistent grammar here means "severity is critical"
means exactly the same thing whether the rows came from alerting or
validation -- which matters more on a dashboard than in a report,
because a dashboard-wide filter fans out across every widget at once.

Deliberately identical to ``services/reporting-service``'s own filter
engine, including its operator semantics. Two subtly different filter
grammars in one platform would be worse than one duplicated module:
a saved filter that behaves differently on a dashboard than in the
report built from the same data is a correctness problem, not a
convenience one.

The cost is that a source's own coarse filters should still be used
where they exist -- that is what
:class:`~app.widgets.schema.WidgetQuery.params` is for -- so this layer
refines a result set rather than replacing server-side filtering with a
full table scan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.models.enums import FilterOperator

_NO_OPERAND = frozenset({FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL})
_SEQUENCE_OPERANDS = frozenset({FilterOperator.IN, FilterOperator.NOT_IN})
_BETWEEN_OPERANDS = 2


@dataclass(frozen=True, slots=True)
class FilterClause:
    """One field/operator/value comparison."""

    field: str
    operator: FilterOperator
    value: Any = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FilterClause:
        """Build a clause from its stored JSON form.

        Raises:
            ValidationError: If the clause is malformed.
        """
        field = raw.get("field")
        if not field or not isinstance(field, str):
            raise ValidationError(f"Filter clause requires a 'field': {raw!r}.")
        raw_operator = raw.get("operator", FilterOperator.EQUALS)
        try:
            operator = FilterOperator(raw_operator)
        except ValueError as exc:
            valid = ", ".join(sorted(str(member) for member in FilterOperator))
            raise ValidationError(
                f"Filter on {field!r} has unknown operator {raw_operator!r}. Valid: {valid}."
            ) from exc

        value = raw.get("value")
        if operator in _SEQUENCE_OPERANDS and not isinstance(value, list | tuple):
            raise ValidationError(
                f"Filter on {field!r} with operator {operator} requires a list value."
            )
        if operator is FilterOperator.BETWEEN and (
            not isinstance(value, list | tuple) or len(value) != _BETWEEN_OPERANDS
        ):
            raise ValidationError(
                f"Filter on {field!r} with operator 'between' requires exactly two values."
            )
        if operator not in _NO_OPERAND and value is None:
            raise ValidationError(f"Filter on {field!r} with operator {operator} requires a value.")
        return cls(field=field, operator=operator, value=value)


def _resolve(row: dict[str, Any], field: str) -> Any:
    """Read ``field`` from *row*, following dots into nested objects.

    A missing path yields ``None`` rather than raising: source services
    legitimately omit optional fields, and one absent key must not fail
    an entire report.
    """
    current: Any = row
    for part in field.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _parse_datetime(text: str) -> Any:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _parse_date(text: str) -> Any:
    return date.fromisoformat(text[:10])


_PARSERS: tuple[tuple[type, Callable[[str], Any]], ...] = (
    (datetime, _parse_datetime),
    (date, _parse_date),
    (float, float),
    (int, float),
)
"""Target type to the parser that turns a string into it.

Ordered most-specific first: ``datetime`` subclasses nothing here but
``bool`` subclasses ``int``, and a ``date`` check would otherwise
swallow ``datetime``.
"""


def _parse_like(left: str, right: Any) -> Any | None:
    """Parse *left* into *right*'s own type, or ``None`` if it will not."""
    if isinstance(right, bool):
        return None
    for target, parser in _PARSERS:
        if isinstance(right, target):
            try:
                return parser(left)
            except ValueError:
                return None
    return None


def _comparable(left: Any, right: Any) -> tuple[Any, Any]:
    """Coerce a pair into something orderable, or leave it alone.

    Source services return timestamps as ISO strings, while a bound
    ``date``/``datetime`` parameter is a real object. Comparing those
    directly raises, so the string side is parsed. Anything that does
    not parse is compared as-is and simply will not match, which is
    the honest outcome for genuinely incomparable values.
    """
    if not isinstance(left, str):
        return left, right
    parsed = _parse_like(left, right)
    if parsed is None:
        return left, right
    return parsed, float(right) if isinstance(parsed, float) else right


def _ordered(left: Any, right: Any) -> tuple[Any, Any] | None:
    """Return an orderable pair, or ``None`` if the two cannot be compared."""
    coerced_left, coerced_right = _comparable(left, right)
    try:
        coerced_left < coerced_right  # noqa: B015  -- probing comparability
    except TypeError:
        return None
    return coerced_left, coerced_right


_DIRECT_COMPARATORS: dict[FilterOperator, Callable[[Any, Any], bool]] = {
    FilterOperator.EQUALS: lambda actual, expected: str(actual) == str(expected),
    FilterOperator.NOT_EQUALS: lambda actual, expected: str(actual) != str(expected),
    FilterOperator.IN: lambda actual, expected: any(str(actual) == str(i) for i in expected),
    FilterOperator.NOT_IN: lambda actual, expected: all(str(actual) != str(i) for i in expected),
    FilterOperator.CONTAINS: lambda actual, expected: str(expected).lower() in str(actual).lower(),
    FilterOperator.STARTS_WITH: (
        lambda actual, expected: str(actual).lower().startswith(str(expected).lower())
    ),
}
"""Operators compared on the string form, independent of ordering.

A dispatch table rather than a chain of branches: each operator's
meaning is one readable line, and adding one cannot accidentally fall
through to another's behaviour.
"""

_ORDERED_COMPARATORS: dict[FilterOperator, Callable[[Any, Any], bool]] = {
    FilterOperator.GREATER_THAN: lambda left, right: bool(left > right),
    FilterOperator.GREATER_OR_EQUAL: lambda left, right: bool(left >= right),
    FilterOperator.LESS_THAN: lambda left, right: bool(left < right),
    FilterOperator.LESS_OR_EQUAL: lambda left, right: bool(left <= right),
}
"""Operators needing a genuine ordering, applied after coercion."""


def _null_verdict(actual: Any, operator: FilterOperator) -> bool | None:
    """Resolve the null-related cases, or ``None`` to keep comparing.

    A missing value satisfies "not equals"/"not in" -- it is genuinely
    not that value -- but nothing else.
    """
    if operator is FilterOperator.IS_NULL:
        return actual is None
    if operator is FilterOperator.IS_NOT_NULL:
        return actual is not None
    if actual is None:
        return operator in (FilterOperator.NOT_EQUALS, FilterOperator.NOT_IN)
    return None


def _matches_between(actual: Any, bounds: Any) -> bool:
    """Whether *actual* falls within an inclusive two-element range."""
    low = _ordered(actual, bounds[0])
    high = _ordered(actual, bounds[1])
    if low is None or high is None:
        return False
    return bool(low[0] >= low[1]) and bool(high[0] <= high[1])


def matches(row: dict[str, Any], clause: FilterClause) -> bool:
    """Whether one row satisfies one clause."""
    actual = _resolve(row, clause.field)

    null_verdict = _null_verdict(actual, clause.operator)
    if null_verdict is not None:
        return null_verdict

    direct = _DIRECT_COMPARATORS.get(clause.operator)
    if direct is not None:
        return direct(actual, clause.value)
    if clause.operator is FilterOperator.BETWEEN:
        return _matches_between(actual, clause.value)

    ordered = _ORDERED_COMPARATORS.get(clause.operator)
    if ordered is None:  # pragma: no cover -- every member handled above
        return False
    pair = _ordered(actual, clause.value)
    return False if pair is None else bool(ordered(pair[0], pair[1]))


def parse_clauses(raw: Sequence[dict[str, Any]]) -> list[FilterClause]:
    """Parse stored filter JSON into clauses.

    Raises:
        ValidationError: If any clause is malformed.
    """
    return [FilterClause.from_dict(entry) for entry in raw]


def apply_filters(
    rows: Iterable[dict[str, Any]], clauses: Sequence[FilterClause]
) -> list[dict[str, Any]]:
    """Return the rows satisfying **every** clause.

    Clauses combine with AND. That is the only combination docs/048's
    filter list implies, and offering OR without an explicit grouping
    syntax would make "environment=prod, status=firing" ambiguous.
    """
    if not clauses:
        return list(rows)
    return [row for row in rows if all(matches(row, clause) for clause in clauses)]


__all__ = ["FilterClause", "apply_filters", "matches", "parse_clauses"]
