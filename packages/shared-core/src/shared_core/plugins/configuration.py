"""Plugin configuration.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN MANIFEST":
Configuration Schema. Per "AUDIT": Configuration Changes. A lightweight
schema -- per-field type, required flag, default value -- validated
against a plugin's actual runtime configuration; not a full JSON Schema
implementation (no ``$ref``/``oneOf``/pattern constraints), since
docs/029 asks for "a configuration schema" a manifest declares, not
conformance to any particular schema standard, and every field type
this framework's own manifests need (string/int/float/bool/list/dict)
is covered by Python's own built-in types.
"""

from __future__ import annotations

from typing import Any

from shared_core.plugins.exceptions import InvalidManifestError

_TYPE_NAMES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate_configuration(configuration: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Validate *configuration* against *schema*, filling in declared defaults.

    *schema* maps a field name to a spec dict: e.g.
    ``{"type": "string", "required": True}`` or ``{"type": "integer",
    "default": 10}``. Returns a new dict with any missing, non-required
    field filled in from its schema default.

    Raises:
        InvalidManifestError: If a required field is missing, or a
            present field's value doesn't match its declared type.
    """
    resolved = dict(configuration)
    for field_name, spec in schema.items():
        if field_name not in resolved:
            if spec.get("required", False):
                raise InvalidManifestError(
                    f"Configuration is missing required field {field_name!r}."
                )
            if "default" in spec:
                resolved[field_name] = spec["default"]
            continue
        expected_type_name = spec.get("type")
        expected_type = _TYPE_NAMES.get(expected_type_name) if expected_type_name else None
        if expected_type is not None and not isinstance(resolved[field_name], expected_type):
            raise InvalidManifestError(
                f"Configuration field {field_name!r} must be of type "
                f"{expected_type_name!r}, got {type(resolved[field_name]).__name__!r}."
            )
    return resolved


class PluginConfigurationStore:
    """Tracks each installed plugin's current runtime configuration."""

    def __init__(self) -> None:
        self._configurations: dict[str, dict[str, Any]] = {}

    def set(
        self,
        plugin_id: str,
        configuration: dict[str, Any],
        *,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Set *plugin_id*'s configuration, validating against *schema* if given.

        Covers "Configuration Changes" from docs/029 "AUDIT" -- pair
        with :func:`shared_core.plugins.audit.audit_configuration_change`.
        """
        resolved = validate_configuration(configuration, schema) if schema else dict(configuration)
        self._configurations[plugin_id] = resolved
        return resolved

    def get(self, plugin_id: str) -> dict[str, Any]:
        """*plugin_id*'s current configuration (an empty dict if never set)."""
        return dict(self._configurations.get(plugin_id, {}))


__all__ = ["PluginConfigurationStore", "validate_configuration"]
