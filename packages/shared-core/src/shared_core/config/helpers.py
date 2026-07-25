"""Type-coercion and interpolation helpers backing the Configuration API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from shared_core.config.exceptions import (
    CircularConfigurationError,
    InvalidTypeError,
    MissingVariableError,
)
from shared_core.helpers.string_helper import mask_string

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "n"})
_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SECRET_KEY_PATTERN = re.compile(r"(password|secret|key|token)", re.IGNORECASE)


def coerce_bool(key: str, value: object) -> bool:
    """Coerce *value* to ``bool``, raising :class:`InvalidTypeError` on failure."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise InvalidTypeError(key, "bool", value)


def coerce_int(key: str, value: object) -> int:
    """Coerce *value* to ``int``, raising :class:`InvalidTypeError` on failure."""
    if isinstance(value, bool):
        raise InvalidTypeError(key, "int", value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise InvalidTypeError(key, "int", value) from exc


def coerce_float(key: str, value: object) -> float:
    """Coerce *value* to ``float``, raising :class:`InvalidTypeError` on failure."""
    if isinstance(value, bool):
        raise InvalidTypeError(key, "float", value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise InvalidTypeError(key, "float", value) from exc


def coerce_list(key: str, value: object, *, separator: str = ",") -> list[str]:
    """Coerce *value* to a ``list[str]``, splitting strings on *separator*."""
    if isinstance(value, list):
        return value
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split(separator) if item.strip()]


def coerce_dict(key: str, value: object) -> dict[str, Any]:
    """Coerce *value* to a ``dict``, parsing strings as JSON objects."""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise InvalidTypeError(key, "dict", value) from exc
    if not isinstance(parsed, dict):
        raise InvalidTypeError(key, "dict", value)
    return parsed


def mask_config_value(key: str, value: object) -> str:
    """Mask *value* for safe logging if *key* looks like it holds a secret."""
    text = str(value)
    if _SECRET_KEY_PATTERN.search(key):
        return mask_string(text, visible_chars=4)
    return text


def interpolate(
    value: str,
    resolve: Callable[[str], str | None],
    *,
    _seen: frozenset[str] = frozenset(),
) -> str:
    """Resolve ``${VAR_NAME}`` references in *value* using *resolve*.

    Raises:
        MissingVariableError: If a referenced variable cannot be resolved.
        CircularConfigurationError: If a variable directly or indirectly
            references itself.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in _seen:
            raise CircularConfigurationError(name)
        resolved = resolve(name)
        if resolved is None:
            raise MissingVariableError(name)
        return interpolate(resolved, resolve, _seen=_seen | {name})

    return _VAR_PATTERN.sub(_replace, value)
