"""Payload/header transformation (docs/057 "PAYLOAD TRANSFORMATION").

Reuses `shared_core.notifications.renderer`'s own choice of a
*sandboxed* Jinja2 environment for template rendering (arbitrary,
caller-authored template strings must never execute arbitrary code) --
but not its ``Template``/``RenderedNotification`` wrapper types, which
are shaped around a notification's own subject/body pair, not a single
templated payload field. This module's own ``render_template`` is a
thin, generic single-string wrapper around the same
``jinja2.sandbox.SandboxedEnvironment`` primitive.

Every other transformation kind here (JSON mapping, header mapping,
field rename/removal/enrichment, metadata injection, version
conversion) is a genuine gap -- no primitive for reshaping an arbitrary
JSON payload exists anywhere in `shared_core`.
"""

from __future__ import annotations

import copy
from typing import Any

from jinja2.sandbox import SandboxedEnvironment

from app.models.enums import TransformationKind

_jinja_env = SandboxedEnvironment(autoescape=False)


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _delete_path(payload: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def apply_json_mapping(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Map fields from source paths to destination paths, per ``config["mappings"]``.

    Each mapping: ``{"from": "user.email", "to": "recipient"}``.
    """
    result = copy.deepcopy(payload)
    for mapping in config.get("mappings", []):
        value = _get_path(payload, mapping["from"])
        if value is not None:
            _set_path(result, mapping["to"], value)
    return result


def apply_header_mapping(headers: dict[str, str], config: dict[str, Any]) -> dict[str, str]:
    """Add/remove headers per ``config`` (``{"add": {...}, "remove": [...]}``)."""
    result = dict(headers)
    for name in config.get("remove", []):
        for key in [k for k in result if k.lower() == str(name).lower()]:
            result.pop(key, None)
    for name, value in config.get("add", {}).items():
        result[str(name)] = str(value)
    return result


def apply_field_rename(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Rename fields per ``config["renames"]`` (``{"from": "old_key", "to": "new_key"}``)."""
    result = copy.deepcopy(payload)
    for rename in config.get("renames", []):
        value = _get_path(result, rename["from"])
        if value is not None:
            _delete_path(result, rename["from"])
            _set_path(result, rename["to"], value)
    return result


def apply_field_removal(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Remove every path listed in ``config["fields"]``."""
    result = copy.deepcopy(payload)
    for path in config.get("fields", []):
        _delete_path(result, path)
    return result


def apply_field_enrichment(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Add static fields from ``config["fields"]``, never overwriting an existing value."""
    result = copy.deepcopy(payload)
    for path, value in config.get("fields", {}).items():
        if _get_path(result, path) is None:
            _set_path(result, path, value)
    return result


def render_template(template_source: str, variables: dict[str, Any]) -> str:
    """Render *template_source* (Jinja2) against *variables*, sandboxed.

    Raises:
        jinja2.TemplateError: If *template_source* is malformed, or
            rendering fails for any other reason.
    """
    template = _jinja_env.from_string(template_source)
    return template.render(**variables)


def apply_template_rendering(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Render ``config["template"]`` against *payload*, storing it at ``config["target_field"]``."""
    result = copy.deepcopy(payload)
    rendered = render_template(config["template"], payload)
    _set_path(result, config.get("target_field", "rendered"), rendered)
    return result


def apply_metadata_injection(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Inject platform-standard metadata (delivery id, correlation id, timestamp) into a payload."""
    result = copy.deepcopy(payload)
    metadata = result.setdefault("_webhook_metadata", {})
    metadata.update(config.get("metadata", {}))
    return result


def apply_version_conversion(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Set the payload's own schema version field, per ``config["target_version"]``."""
    result = copy.deepcopy(payload)
    _set_path(result, config.get("version_field", "schema_version"), config["target_version"])
    return result


_PAYLOAD_TRANSFORMERS = {
    TransformationKind.JSON_MAPPING: apply_json_mapping,
    TransformationKind.FIELD_RENAME: apply_field_rename,
    TransformationKind.FIELD_REMOVAL: apply_field_removal,
    TransformationKind.FIELD_ENRICHMENT: apply_field_enrichment,
    TransformationKind.TEMPLATE_RENDERING: apply_template_rendering,
    TransformationKind.METADATA_INJECTION: apply_metadata_injection,
    TransformationKind.VERSION_CONVERSION: apply_version_conversion,
}


def apply_transformation(
    payload: dict[str, Any], *, kind: TransformationKind, config: dict[str, Any]
) -> dict[str, Any]:
    """Apply one transformation rule's own payload effect.

    ``HEADER_MAPPING`` and ``CUSTOM`` are not payload transformers --
    header mapping is applied separately via :func:`apply_header_mapping`,
    and ``CUSTOM`` has no fixed shape for this platform to interpret
    generically, per docs/057's own "Custom Transformations" naming it
    as an extension point rather than a concrete behaviour.
    """
    transformer = _PAYLOAD_TRANSFORMERS.get(kind)
    return transformer(payload, config) if transformer else payload


__all__ = [
    "apply_field_enrichment",
    "apply_field_removal",
    "apply_field_rename",
    "apply_header_mapping",
    "apply_json_mapping",
    "apply_metadata_injection",
    "apply_template_rendering",
    "apply_transformation",
    "apply_version_conversion",
    "render_template",
]
