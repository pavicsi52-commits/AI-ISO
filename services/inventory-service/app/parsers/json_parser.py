"""JSON import/export parsing."""

from __future__ import annotations

import json
from typing import Any

from shared_core.exceptions.validation import ValidationError


def parse_json_rows(content: bytes) -> list[dict[str, Any]]:
    """Parse *content* (a JSON array of row objects) into a list of row dicts.

    Raises:
        ValidationError: If *content* isn't a JSON array of objects.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValidationError("JSON import must be an array of row objects.")
    return data


def write_json_rows(rows: list[dict[str, Any]]) -> bytes:
    """Serialize *rows* to a JSON array."""
    return json.dumps(rows, default=str, indent=2).encode("utf-8")


__all__ = ["parse_json_rows", "write_json_rows"]
