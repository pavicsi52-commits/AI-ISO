"""Data transformation (docs/058 "DATA TRANSFORMATION").

A genuine gap -- nothing in `shared_core` converts between JSON/XML/CSV/
YAML or applies field mapping/schema validation/enrichment/filtering/
aggregation/normalization to a payload (`shared_core.helpers.json_helper`
is basic serialization only; `shared_core.requests.import_export
.DataFormat` is a bare enum with no XML member and no conversion logic).
Built new, pure, and dependency-free beyond the standard library plus
PyYAML (already a transitive `shared_core` dependency).

**Canonical representation.** Every format converts to/from a plain
Python value: a JSON/YAML document becomes whatever `json.loads`/
`yaml.safe_load` returns (usually a `dict`); CSV becomes a
`list[dict[str, str]]` (one dict per row, via `csv.DictReader`); XML
becomes a `dict` via a recursive element walk (attributes prefixed
`@`, text content under `"#text"` only when an element also has
children or attributes, otherwise the element's own value is its text
directly). Every rule-based operation below operates on this canonical
form, never on the serialized string -- format conversion and semantic
transformation are deliberately independent steps.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import yaml

from app.models.enums import DataFormat, TransformationKind

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

_TYPE_NAMES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a dotted field path (e.g. ``"address.city"``) against *data*."""
    current = data
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted field path on *data*, creating intermediate dicts as needed."""
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value


def _delete_path(data: dict[str, Any], path: str) -> None:
    """Delete a dotted field path from *data*, if it exists."""
    parts = path.split(".")
    current: Any = data
    for part in parts[:-1]:
        if not isinstance(current, Mapping) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


# ---- format conversion -------------------------------------------------------------


def _xml_element_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children and not element.attrib:
        return element.text.strip() if element.text and element.text.strip() else None
    value: dict[str, Any] = {f"@{k}": v for k, v in element.attrib.items()}
    for child in children:
        child_value = _xml_element_to_value(child)
        if child.tag in value:
            existing = value[child.tag]
            if isinstance(existing, list):
                existing.append(child_value)
            else:
                value[child.tag] = [existing, child_value]
        else:
            value[child.tag] = child_value
    if element.text and element.text.strip():
        value["#text"] = element.text.strip()
    return value


def _value_to_xml_element(tag: str, value: Any) -> ET.Element:
    element = ET.Element(tag)
    if isinstance(value, Mapping):
        for key, sub_value in value.items():
            if key.startswith("@"):
                element.set(key[1:], str(sub_value))
            elif key == "#text":
                element.text = str(sub_value)
            elif isinstance(sub_value, list):
                for item in sub_value:
                    element.append(_value_to_xml_element(key, item))
            else:
                element.append(_value_to_xml_element(key, sub_value))
    else:
        element.text = "" if value is None else str(value)
    return element


def parse_document(raw: str, data_format: DataFormat) -> Any:
    """Parse *raw* text in *data_format* into this engine's canonical representation."""
    if data_format == DataFormat.JSON:
        return json.loads(raw) if raw.strip() else {}
    if data_format == DataFormat.YAML:
        return yaml.safe_load(raw) or {}
    if data_format == DataFormat.CSV:
        return list(csv.DictReader(io.StringIO(raw)))
    root = ET.fromstring(raw)
    return {root.tag: _xml_element_to_value(root)}


def render_document(data: Any, data_format: DataFormat, *, xml_root: str = "root") -> str:
    """Render this engine's canonical representation as *data_format* text."""
    if data_format == DataFormat.JSON:
        return json.dumps(data)
    if data_format == DataFormat.YAML:
        return yaml.safe_dump(data, sort_keys=False)
    if data_format == DataFormat.CSV:
        rows = data if isinstance(data, list) else [data]
        if not rows:
            return ""
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
    if isinstance(data, Mapping) and len(data) == 1:
        ((tag, value),) = data.items()
        element = _value_to_xml_element(tag, value)
    else:
        element = _value_to_xml_element(xml_root, data)
    return ET.tostring(element, encoding="unicode")


# ---- rule-based operations ----------------------------------------------------------


def evaluate_rule(attributes: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Evaluate one ``{"field", "operator", "value"}`` rule against *attributes*.

    Raises:
        ValueError: If ``rule["operator"]`` is not a recognised operator.
    """
    operator = rule.get("operator", "eq")
    if operator not in _OPERATORS:
        raise ValueError(f"Unrecognised transformation operator: {operator!r}")
    actual = _resolve_path(attributes, str(rule.get("field", "")))
    expected = rule.get("value")
    if operator == "exists":
        return actual is not None
    if actual is None:
        return False
    return _COMPARATORS[operator](actual, expected)


def apply_field_mapping(data: Mapping[str, Any], mapping: Mapping[str, str]) -> dict[str, Any]:
    """Move/rename fields per *mapping* (``{source_path: target_path}``)."""
    result: dict[str, Any] = dict(data)
    for source, target in mapping.items():
        value = _resolve_path(data, source)
        if value is not None:
            _set_path(result, target, value)
            if source != target:
                _delete_path(result, source)
    return result


def apply_filtering(
    rows: Sequence[Mapping[str, Any]], rules: Sequence[Mapping[str, Any]]
) -> list[Any]:
    """Keep only the rows matching every rule in *rules* (empty *rules* keeps everything)."""
    if not rules:
        return list(rows)
    return [row for row in rows if all(evaluate_rule(row, rule) for rule in rules)]


def apply_enrichment(data: Mapping[str, Any], enrichment: Mapping[str, Any]) -> dict[str, Any]:
    """Merge *enrichment*'s static fields into *data*, without overwriting existing keys."""
    result = dict(data)
    for path, value in enrichment.items():
        if _resolve_path(result, path) is None:
            _set_path(result, path, value)
    return result


def apply_aggregation(
    rows: Sequence[Mapping[str, Any]], *, group_by: str, aggregations: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Group *rows* by *group_by* and compute each ``{field: "sum"|"avg"|"count"|"min"|"max"}``."""
    groups: dict[Any, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = _resolve_path(row, group_by)
        groups.setdefault(key, []).append(row)

    results: list[dict[str, Any]] = []
    for key, members in groups.items():
        entry: dict[str, Any] = {group_by: key, "count": len(members)}
        for field, operation in aggregations.items():
            values = [v for v in (_resolve_path(m, field) for m in members) if v is not None]
            if operation == "count":
                entry[field] = len(values)
            elif not values:
                entry[field] = None
            elif operation == "sum":
                entry[field] = sum(values)
            elif operation == "avg":
                entry[field] = sum(values) / len(values)
            elif operation == "min":
                entry[field] = min(values)
            elif operation == "max":
                entry[field] = max(values)
        results.append(entry)
    return results


def apply_normalization(data: Mapping[str, Any], rules: Mapping[str, str]) -> dict[str, Any]:
    """Apply a per-field ``"lowercase"``/``"uppercase"``/``"trim"``/``"stringify"`` rule."""
    result = dict(data)
    for path, rule in rules.items():
        value = _resolve_path(result, path)
        if value is None:
            continue
        if rule == "lowercase" and isinstance(value, str):
            _set_path(result, path, value.lower())
        elif rule == "uppercase" and isinstance(value, str):
            _set_path(result, path, value.upper())
        elif rule == "trim" and isinstance(value, str):
            _set_path(result, path, value.strip())
        elif rule == "stringify":
            _set_path(result, path, str(value))
    return result


def validate_schema(data: Mapping[str, Any], schema: Mapping[str, Any]) -> list[str]:
    """Structurally validate *data* against a lightweight ``{"required": [...],
    "properties": {field: {"type": ...}}}`` schema.

    Real structural checking (required-field presence, basic type
    matching) -- never execution of caller-supplied code, and never a
    claim of full JSON Schema draft compliance. Returns every violation
    found; an empty list means *data* is valid.
    """
    violations: list[str] = []
    for field in schema.get("required", []):
        if _resolve_path(data, field) is None:
            violations.append(f"Missing required field: {field}")

    properties: Mapping[str, Any] = schema.get("properties", {})
    for field, spec in properties.items():
        value = _resolve_path(data, field)
        if value is None:
            continue
        expected_type = spec.get("type")
        python_type = _TYPE_NAMES.get(expected_type)
        if python_type is not None and not isinstance(value, python_type):
            violations.append(
                f"Field {field!r} expected type {expected_type!r}, got {type(value).__name__!r}"
            )
    return violations


def _apply_format_conversion(data: Any, config: Mapping[str, Any]) -> Any:
    source_format = DataFormat(config.get("source_format", DataFormat.JSON))
    target_format = DataFormat(config.get("target_format", DataFormat.JSON))
    parsed = parse_document(data, source_format) if isinstance(data, str) else data
    return render_document(parsed, target_format)


_TRANSFORMATIONS: dict[TransformationKind, Callable[[Any, Mapping[str, Any]], Any]] = {
    TransformationKind.FIELD_MAPPING: lambda data, config: apply_field_mapping(
        data, config.get("mapping", {})
    ),
    TransformationKind.SCHEMA_VALIDATION: lambda data, config: {
        "violations": validate_schema(data, config.get("schema", {}))
    },
    TransformationKind.ENRICHMENT: lambda data, config: apply_enrichment(
        data, config.get("fields", {})
    ),
    TransformationKind.FILTERING: lambda data, config: apply_filtering(
        data, config.get("rules", [])
    ),
    TransformationKind.AGGREGATION: lambda data, config: apply_aggregation(
        data, group_by=config.get("group_by", ""), aggregations=config.get("aggregations", {})
    ),
    TransformationKind.NORMALIZATION: lambda data, config: apply_normalization(
        data, config.get("rules", {})
    ),
    TransformationKind.FORMAT_CONVERSION: _apply_format_conversion,
}


def apply_transformation(data: Any, *, kind: TransformationKind, config: Mapping[str, Any]) -> Any:
    """Dispatch *data* through one transformation rule of *kind*, per *config*."""
    return _TRANSFORMATIONS[kind](data, config)


__all__ = [
    "apply_aggregation",
    "apply_enrichment",
    "apply_field_mapping",
    "apply_filtering",
    "apply_normalization",
    "apply_transformation",
    "evaluate_rule",
    "parse_document",
    "render_document",
    "validate_schema",
]
