"""JSON serialization helper functions."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_json(value: Any) -> str:
    """Serialize a value to a JSON string, handling datetime/UUID."""
    return json.dumps(value, default=_default)


def from_json(value: str | bytes) -> Any:
    """Deserialize a JSON string (or the raw bytes a client returned)."""
    return json.loads(value)


def safe_from_json(value: str | bytes, default: Any = None) -> Any:
    """Deserialize a JSON string, returning ``default`` on parse failure."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
