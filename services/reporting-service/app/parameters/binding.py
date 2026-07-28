"""Report parameter binding and coercion ("PARAMETERS").

Parameters arrive over HTTP as JSON, so an ``integer`` parameter may
turn up as ``"7"`` and a ``date`` as ``"2026-07-28"``. This module
coerces each supplied value to its declared type once, at the boundary,
so every consumer downstream -- filters, queries, templates -- works
with real Python types rather than re-parsing strings and disagreeing
about what a value means.

Coercion is deliberately strict about *losing information* and lenient
about *representation*: ``"7"`` becomes ``7`` because that is
unambiguous, but ``7.5`` is rejected for an ``integer`` because
silently truncating a value a user typed is how wrong numbers end up in
a compliance report.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.models.enums import ParameterKind
from app.models.report_parameter import ReportParameter

_TRUE = frozenset({"true", "t", "yes", "y", "1", "on"})
_FALSE = frozenset({"false", "f", "no", "n", "0", "off"})


@dataclass(frozen=True, slots=True)
class BoundParameters:
    """Parameter values coerced to their declared types."""

    values: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        """Return one bound value, or *default*."""
        return self.values.get(key, default)

    def as_query_params(self) -> dict[str, str]:
        """Render every value as a string, for use as HTTP query params.

        ``None`` is dropped rather than sent as the literal ``"None"``,
        which is what an unset optional filter should mean.
        """
        rendered: dict[str, str] = {}
        for key, value in self.values.items():
            if value is None:
                continue
            if isinstance(value, datetime | date):
                rendered[key] = value.isoformat()
            elif isinstance(value, bool):
                rendered[key] = "true" if value else "false"
            elif isinstance(value, list | tuple):
                rendered[key] = ",".join(str(item) for item in value)
            else:
                rendered[key] = str(value)
        return rendered


def _coerce_bool(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValidationError(f"Parameter {key!r} expects a boolean, got {value!r}.")


def _coerce_int(key: str, value: Any) -> int:
    if isinstance(value, bool):
        # bool subclasses int in Python; accepting True as 1 here would
        # silently turn a checkbox into a row limit.
        raise ValidationError(f"Parameter {key!r} expects an integer, got a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != int(value):
            raise ValidationError(
                f"Parameter {key!r} expects an integer; {value!r} would lose precision."
            )
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Parameter {key!r} expects an integer, got {value!r}.") from exc


def _coerce_number(key: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"Parameter {key!r} expects a number, got a boolean.")
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Parameter {key!r} expects a number, got {value!r}.") from exc


def _coerce_datetime(key: str, value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(
            f"Parameter {key!r} expects an ISO-8601 datetime, got {value!r}."
        ) from exc


def _coerce_date(key: str, value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValidationError(
            f"Parameter {key!r} expects an ISO-8601 date, got {value!r}."
        ) from exc


def _coerce_uuid(key: str, value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Parameter {key!r} expects a UUID, got {value!r}.") from exc


_COERCERS: dict[ParameterKind, Callable[[str, Any], Any]] = {
    ParameterKind.STRING: lambda _key, value: str(value),
    ParameterKind.ENUM: lambda _key, value: str(value),
    ParameterKind.INTEGER: _coerce_int,
    ParameterKind.NUMBER: _coerce_number,
    ParameterKind.BOOLEAN: _coerce_bool,
    ParameterKind.DATE: _coerce_date,
    ParameterKind.DATETIME: _coerce_datetime,
    ParameterKind.UUID: _coerce_uuid,
}
"""Declared kind to its coercer.

A table rather than a branch chain, so a newly added
:class:`ParameterKind` that nobody wired up fails loudly here instead
of silently falling through to ``str``.
"""


def coerce(key: str, kind: ParameterKind, value: Any) -> Any:
    """Coerce one supplied value to its declared *kind*.

    Raises:
        ValidationError: If the value cannot be represented as *kind*
            without losing information, or the kind is unsupported.
    """
    if value is None:
        return None
    coercer = _COERCERS.get(kind)
    if coercer is None:
        raise ValidationError(f"Parameter {key!r} has unsupported kind {kind!r}.")
    return coercer(key, value)


def bind(declared: list[ReportParameter], supplied: dict[str, Any]) -> BoundParameters:
    """Bind *supplied* values against *declared* parameters.

    Applies defaults, enforces required-ness and allowed values, and
    coerces every value to its declared type.

    Unknown keys are rejected rather than ignored. A typo'd parameter
    name that silently does nothing produces a report that looks
    correct but was filtered differently than the user asked for --
    a far worse failure than a clear error.

    Raises:
        ValidationError: If a required parameter is missing, an unknown
            one was supplied, a value is not coercible, or a value is
            outside its declared ``allowed_values``.
    """
    declared_by_key = {parameter.key: parameter for parameter in declared}

    unknown = sorted(set(supplied) - set(declared_by_key))
    if unknown:
        raise ValidationError(
            f"Unknown report parameter(s): {', '.join(unknown)}. "
            f"Declared: {', '.join(sorted(declared_by_key)) or 'none'}."
        )

    bound: dict[str, Any] = {}
    missing: list[str] = []
    for key, parameter in declared_by_key.items():
        raw = supplied.get(key, parameter.default_value)
        if raw is None:
            if parameter.required:
                missing.append(key)
            bound[key] = None
            continue

        kind = (
            parameter.kind
            if isinstance(parameter.kind, ParameterKind)
            else ParameterKind(parameter.kind)
        )
        value = coerce(key, kind, raw)
        if parameter.allowed_values and value not in parameter.allowed_values:
            allowed = ", ".join(str(item) for item in parameter.allowed_values)
            raise ValidationError(f"Parameter {key!r} must be one of: {allowed}. Got {value!r}.")
        bound[key] = value

    if missing:
        raise ValidationError(
            f"Missing required report parameter(s): {', '.join(sorted(missing))}."
        )
    return BoundParameters(values=bound)


__all__ = ["BoundParameters", "bind", "coerce"]
