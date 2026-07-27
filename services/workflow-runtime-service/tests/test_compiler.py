"""Tests for :mod:`app.services.compiler` -- real DAG compilation via
``shared_core.workflow``, no mocking of the SDK itself.
"""

from __future__ import annotations

from typing import Any

import pytest
from shared_core.workflow import CycleDetectedError, InvalidWorkflowDefinitionError

from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_version import WorkflowVersion
from app.services.compiler import compile_version, edges_to_sdk_dicts, to_sdk_definition
from tests.conftest import linear_nodes_and_edges


def _definition(**overrides: object) -> WorkflowDefinition:
    # A transient (never-flushed) model instance never runs its own
    # mapped_column(default=...) callables -- those only fire at INSERT
    # time -- so every column to_sdk_definition() reads must be given
    # explicitly here rather than relying on the column's own default.
    base: dict[str, object] = {
        "workflow_key": "wf-1",
        "name": "Sample",
        "description": None,
        "owner": None,
        "tags": [],
        "default_variables": {},
    }
    base.update(overrides)
    definition = WorkflowDefinition(**base)
    return definition


def _version(
    definition: WorkflowDefinition, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> WorkflowVersion:
    return WorkflowVersion(
        definition_id=definition.id,
        version_number="1.0.0",
        nodes=nodes,
        edges=edges,
        compiled_execution_plan=[],
    )


class TestEdgesToSdkDicts:
    def test_translates_from_and_to_keys(self) -> None:
        edges = [{"from_node_id": "a", "to_node_id": "b"}]
        assert edges_to_sdk_dicts(edges) == [{"from": "a", "to": "b"}]

    def test_carries_optional_condition_and_label(self) -> None:
        edges = [{"from_node_id": "a", "to_node_id": "b", "condition": "x > 1", "label": "yes"}]
        result = edges_to_sdk_dicts(edges)
        assert result == [{"from": "a", "to": "b", "condition": "x > 1", "label": "yes"}]


class TestToSdkDefinition:
    def test_builds_a_real_workflow_definition(self) -> None:
        nodes, edges = linear_nodes_and_edges()
        definition = _definition()
        version = _version(definition, nodes, edges)

        sdk_definition = to_sdk_definition(definition, version)

        assert sdk_definition.workflow_id == "wf-1"
        assert len(sdk_definition.nodes) == 3
        assert len(sdk_definition.edges) == 2


class TestCompileVersion:
    def test_compiles_a_valid_linear_dag(self) -> None:
        nodes, edges = linear_nodes_and_edges()
        definition = _definition()
        version = _version(definition, nodes, edges)

        compiled = compile_version(definition, version)

        assert compiled.execution_plan == [["start"], ["task"], ["end"]]

    def test_raises_on_missing_hosts_shape(self) -> None:
        definition = _definition()
        version = _version(
            definition,
            nodes=[{"node_id": "a", "node_type": "task", "name": "a"}],
            edges=[],
        )
        with pytest.raises(InvalidWorkflowDefinitionError):
            compile_version(definition, version)

    def test_raises_on_cycle(self) -> None:
        definition = _definition()
        nodes = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "a", "node_type": "task", "name": "a"},
            {"node_id": "b", "node_type": "task", "name": "b"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "a"},
            {"from_node_id": "a", "to_node_id": "b"},
            {"from_node_id": "b", "to_node_id": "a"},
            {"from_node_id": "b", "to_node_id": "end"},
        ]
        version = _version(definition, nodes, edges)
        with pytest.raises(CycleDetectedError):
            compile_version(definition, version)
