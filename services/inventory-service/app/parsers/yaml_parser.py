"""YAML import/export parsing.

No ``shared_core`` wrapper exists for YAML -- ``PyYAML`` is added
directly to this service's own ``pyproject.toml``, matching every
prior AI-IOS import/export service's own identical precedent.
"""

from __future__ import annotations

from typing import Any

import yaml
from shared_core.exceptions.validation import ValidationError


def parse_yaml_rows(content: bytes) -> list[dict[str, Any]]:
    """Parse *content* (a YAML sequence of row mappings) into a list of row dicts.

    Raises:
        ValidationError: If *content* isn't a YAML sequence of mappings.
    """
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValidationError(f"Invalid YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValidationError("YAML import must be a sequence of row mappings.")
    return data


def write_yaml_rows(rows: list[dict[str, Any]]) -> bytes:
    """Serialize *rows* to a YAML sequence."""
    return yaml.safe_dump(rows, default_flow_style=False, sort_keys=False).encode("utf-8")


__all__ = ["parse_yaml_rows", "write_yaml_rows"]
