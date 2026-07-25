"""Tests for :mod:`app.tosca.validator`."""

from __future__ import annotations

import pytest

from app.models.enums import ToscaComponentType
from app.tosca.validator import (
    ToscaValidationError,
    validate_tosca_content,
    validate_tosca_content_or_raise,
)


@pytest.mark.parametrize(
    ("component_type", "content"),
    [
        (
            ToscaComponentType.SERVICE_TEMPLATE,
            {"tosca_definitions_version": "tosca_simple_yaml_1_3", "topology_template": {}},
        ),
        (ToscaComponentType.NODE_TEMPLATE, {"type": "tosca.nodes.Compute"}),
        (ToscaComponentType.RELATIONSHIP_TEMPLATE, {"type": "tosca.relationships.HostedOn"}),
        (ToscaComponentType.POLICY, {"type": "tosca.policies.Scaling"}),
        (ToscaComponentType.SUBSTITUTION_MAPPING, {"node_type": "tosca.nodes.WebServer"}),
        (ToscaComponentType.ARTIFACT, {"type": "tosca.artifacts.File", "file": "script.sh"}),
        (ToscaComponentType.CSAR_PACKAGE, {"entry_definitions": "main.yaml"}),
        (ToscaComponentType.CSAR_PACKAGE, {"tosca_definitions_version": "tosca_simple_yaml_1_3"}),
    ],
)
def test_valid_content_has_no_errors(
    component_type: ToscaComponentType, content: dict[str, object]
) -> None:
    assert validate_tosca_content(component_type, content) == []


@pytest.mark.parametrize(
    ("component_type", "content"),
    [
        (ToscaComponentType.SERVICE_TEMPLATE, {}),
        (ToscaComponentType.SERVICE_TEMPLATE, {"tosca_definitions_version": "x"}),
        (ToscaComponentType.NODE_TEMPLATE, {}),
        (ToscaComponentType.RELATIONSHIP_TEMPLATE, {}),
        (ToscaComponentType.POLICY, {}),
        (ToscaComponentType.SUBSTITUTION_MAPPING, {}),
        (ToscaComponentType.ARTIFACT, {"type": "tosca.artifacts.File"}),
        (ToscaComponentType.ARTIFACT, {}),
        (ToscaComponentType.CSAR_PACKAGE, {}),
    ],
)
def test_invalid_content_returns_errors(
    component_type: ToscaComponentType, content: dict[str, object]
) -> None:
    errors = validate_tosca_content(component_type, content)
    assert errors != []


def test_validate_or_raise_passes_through_valid_content() -> None:
    validate_tosca_content_or_raise(
        ToscaComponentType.NODE_TEMPLATE, {"type": "tosca.nodes.Compute"}
    )


def test_validate_or_raise_raises_on_invalid_content() -> None:
    with pytest.raises(ToscaValidationError, match="missing required key"):
        validate_tosca_content_or_raise(ToscaComponentType.NODE_TEMPLATE, {})
