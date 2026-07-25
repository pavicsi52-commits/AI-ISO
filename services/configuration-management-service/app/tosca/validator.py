"""TOSCA template structural validation.

Per docs/039 "TOSCA INTEGRATION" "Integrate": TOSCA Templates, CSAR
Packages, Node Templates, Relationship Templates, Policies,
Substitution Mappings, Artifacts, Service Templates. Each
:class:`app.models.enums.ToscaComponentType` names a distinct document
shape defined by the OASIS TOSCA Simple Profile in YAML v1.3
specification; this module checks that a template's own ``content``
JSON contains the keys that shape requires before it is persisted,
without pulling in a full third-party TOSCA parser (none of which
target Python 3.13 / TOSCA 1.3 well enough to justify the dependency).
"""

from __future__ import annotations

from typing import Any

from app.models.enums import ToscaComponentType


class ToscaValidationError(Exception):
    """A TOSCA template's content does not match its declared component type."""


_REQUIRED_KEYS: dict[ToscaComponentType, tuple[str, ...]] = {
    ToscaComponentType.SERVICE_TEMPLATE: ("tosca_definitions_version", "topology_template"),
    ToscaComponentType.NODE_TEMPLATE: ("type",),
    ToscaComponentType.RELATIONSHIP_TEMPLATE: ("type",),
    ToscaComponentType.POLICY: ("type",),
    ToscaComponentType.SUBSTITUTION_MAPPING: ("node_type",),
    ToscaComponentType.ARTIFACT: ("type", "file"),
}


def validate_tosca_content(
    component_type: ToscaComponentType, content: dict[str, Any]
) -> list[str]:
    """Return every structural problem found in *content*; empty if valid."""
    if component_type is ToscaComponentType.CSAR_PACKAGE:
        if "entry_definitions" not in content and "tosca_definitions_version" not in content:
            return [
                "csar_package requires either 'entry_definitions' (TOSCA.meta pointer) "
                "or 'tosca_definitions_version'"
            ]
        return []
    return _require_keys(content, component_type.value, *_REQUIRED_KEYS[component_type])


def validate_tosca_content_or_raise(
    component_type: ToscaComponentType, content: dict[str, Any]
) -> None:
    """Raise :class:`ToscaValidationError` if *content* is structurally invalid."""
    errors = validate_tosca_content(component_type, content)
    if errors:
        raise ToscaValidationError("; ".join(errors))


def _require_keys(content: dict[str, Any], label: str, *keys: str) -> list[str]:
    missing = [key for key in keys if key not in content]
    if not missing:
        return []
    return [f"{label} is missing required key(s): {', '.join(missing)}"]


__all__ = ["ToscaValidationError", "validate_tosca_content", "validate_tosca_content_or_raise"]
