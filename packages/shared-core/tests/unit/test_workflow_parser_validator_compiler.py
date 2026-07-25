"""Tests for parser.py, validator.py, compiler.py, and template.py."""

from __future__ import annotations

import pytest
from shared_core.workflow.compiler import compile_workflow
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.exceptions import CycleDetectedError, InvalidWorkflowDefinitionError
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.parser import WorkflowBuilder, parse_dict, parse_json, parse_yaml
from shared_core.workflow.template import WorkflowTemplate
from shared_core.workflow.validator import build_graph, validate_definition

_SIMPLE_DICT = {
    "workflow_id": "wf-1",
    "name": "Sample",
    "version": "1.0.0",
    "nodes": [
        {"node_id": "start", "node_type": "start"},
        {"node_id": "task", "node_type": "task", "config": {"handler": "do_thing"}},
        {"node_id": "end", "node_type": "end"},
    ],
    "edges": [
        {"from": "start", "to": "task"},
        {"from": "task", "to": "end"},
    ],
}

_SIMPLE_YAML = """
workflow_id: wf-1
name: Sample
version: "1.0.0"
nodes:
  - node_id: start
    node_type: start
  - node_id: task
    node_type: task
  - node_id: end
    node_type: end
edges:
  - from: start
    to: task
  - from: task
    to: end
"""

_SIMPLE_JSON = """
{
  "workflow_id": "wf-1",
  "name": "Sample",
  "version": "1.0.0",
  "nodes": [
    {"node_id": "start", "node_type": "start"},
    {"node_id": "task", "node_type": "task"},
    {"node_id": "end", "node_type": "end"}
  ],
  "edges": [
    {"from": "start", "to": "task"},
    {"from": "task", "to": "end"}
  ]
}
"""


# --- parser.py ---


def test_parse_dict_builds_a_workflow_definition() -> None:
    definition = parse_dict(_SIMPLE_DICT)

    assert definition.workflow_id == "wf-1"
    assert len(definition.nodes) == 3
    assert len(definition.edges) == 2


def test_parse_dict_node_config_round_trips() -> None:
    definition = parse_dict(_SIMPLE_DICT)

    task_node = next(node for node in definition.nodes if node.node_id == "task")
    assert task_node.config == {"handler": "do_thing"}


def test_parse_dict_raises_for_a_missing_required_field() -> None:
    broken = {"workflow_id": "wf-1", "name": "Sample"}  # missing "version"/"nodes"

    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_dict(broken)


def test_parse_dict_raises_for_an_invalid_node_type() -> None:
    broken = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [{"node_id": "n1", "node_type": "not-a-real-type"}],
    }

    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_dict(broken)


def test_parse_yaml_builds_a_workflow_definition() -> None:
    definition = parse_yaml(_SIMPLE_YAML)

    assert definition.workflow_id == "wf-1"
    assert len(definition.nodes) == 3


def test_parse_yaml_raises_for_malformed_yaml() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_yaml("nodes: [unterminated")


def test_parse_yaml_raises_when_not_a_mapping() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_yaml("- just\n- a\n- list\n")


def test_parse_json_builds_a_workflow_definition() -> None:
    definition = parse_json(_SIMPLE_JSON)

    assert definition.workflow_id == "wf-1"


def test_parse_json_raises_for_malformed_json() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_json("{not valid json")


def test_parse_json_raises_when_not_a_mapping() -> None:
    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_json("[1, 2, 3]")


def test_workflow_builder_builds_an_equivalent_definition() -> None:
    definition = (
        WorkflowBuilder("wf-1", "Sample")
        .description("A sample workflow")
        .owner("team-a")
        .tag("demo", "test")
        .variable("retries", 3)
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="end"))
        .build()
    )

    assert definition.workflow_id == "wf-1"
    assert definition.description == "A sample workflow"
    assert definition.owner == "team-a"
    assert definition.tags == ("demo", "test")
    assert definition.default_variables == {"retries": 3}
    assert len(definition.nodes) == 2
    assert len(definition.edges) == 1


# --- validator.py ---


def test_build_graph_from_definition() -> None:
    definition = parse_dict(_SIMPLE_DICT)

    graph = build_graph(definition)

    assert set(graph.nodes) == {"start", "task", "end"}


def test_validate_definition_passes_for_a_valid_workflow() -> None:
    definition = parse_dict(_SIMPLE_DICT)

    graph = validate_definition(definition)

    assert set(graph.nodes) == {"start", "task", "end"}


def test_validate_definition_rejects_duplicate_node_ids() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start", "node_type": "start"},
            {"node_id": "start", "node_type": "end"},
        ],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError, match="unique"):
        validate_definition(definition)


def test_validate_definition_rejects_missing_start() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [{"node_id": "end", "node_type": "end"}],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError, match="START"):
        validate_definition(definition)


def test_validate_definition_rejects_multiple_start_nodes() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start1", "node_type": "start"},
            {"node_id": "start2", "node_type": "start"},
            {"node_id": "end", "node_type": "end"},
        ],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError, match="START"):
        validate_definition(definition)


def test_validate_definition_rejects_missing_end() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [{"node_id": "start", "node_type": "start"}],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError, match="END"):
        validate_definition(definition)


def test_validate_definition_rejects_unreachable_nodes() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start", "node_type": "start"},
            {"node_id": "end", "node_type": "end"},
            {"node_id": "orphan", "node_type": "task"},
        ],
        "edges": [{"from": "start", "to": "end"}],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError, match="Unreachable"):
        validate_definition(definition)


def test_validate_definition_rejects_a_cycle() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start", "node_type": "start"},
            {"node_id": "a", "node_type": "task"},
            {"node_id": "end", "node_type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "a"},
            {"from": "a", "to": "a"},
            {"from": "a", "to": "end"},
        ],
    }
    definition = parse_dict(data)

    with pytest.raises(CycleDetectedError):
        validate_definition(definition)


# --- compiler.py ---


def test_compile_workflow_produces_a_graph_and_plan() -> None:
    definition = parse_dict(_SIMPLE_DICT)

    compiled = compile_workflow(definition)

    assert compiled.definition is definition
    assert compiled.execution_plan == [["start"], ["task"], ["end"]]


def test_compile_workflow_raises_for_an_invalid_definition() -> None:
    data = {
        "workflow_id": "wf-1",
        "name": "Sample",
        "version": "1.0.0",
        "nodes": [{"node_id": "start", "node_type": "start"}],
    }
    definition = parse_dict(data)

    with pytest.raises(InvalidWorkflowDefinitionError):
        compile_workflow(definition)


# --- template.py ---


def test_workflow_template_instantiate_substitutes_parameters() -> None:
    template = WorkflowTemplate(
        template_id="tpl-1",
        structure={
            "workflow_id": "${workflow_id}",
            "name": "Sample",
            "version": "1.0.0",
            "nodes": [
                {"node_id": "start", "node_type": "start"},
                {"node_id": "end", "node_type": "end"},
            ],
            "edges": [{"from": "start", "to": "end"}],
        },
        parameters={"workflow_id": "default-id"},
    )

    definition = template.instantiate()

    assert definition.workflow_id == "default-id"


def test_workflow_template_instantiate_overrides_defaults() -> None:
    template = WorkflowTemplate(
        template_id="tpl-1",
        structure={
            "workflow_id": "${workflow_id}",
            "name": "Sample",
            "version": "1.0.0",
            "nodes": [
                {"node_id": "start", "node_type": "start"},
                {"node_id": "end", "node_type": "end"},
            ],
        },
        parameters={"workflow_id": "default-id"},
    )

    definition = template.instantiate(workflow_id="override-id")

    assert definition.workflow_id == "override-id"


def test_workflow_template_instantiate_raises_for_an_undeclared_parameter() -> None:
    template = WorkflowTemplate(
        template_id="tpl-1",
        structure={
            "workflow_id": "${missing_param}",
            "name": "Sample",
            "version": "1.0.0",
            "nodes": [],
        },
    )

    with pytest.raises(InvalidWorkflowDefinitionError):
        template.instantiate()
