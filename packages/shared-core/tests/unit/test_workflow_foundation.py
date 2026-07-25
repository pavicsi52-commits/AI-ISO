"""Tests for variables.py, context.py, nodes.py, edges.py, expressions.py,
conditions.py, graph.py, dag.py, and definition.py.
"""

from __future__ import annotations

import pytest
from shared_core.workflow.conditions import (
    Rule,
    evaluate_if_else,
    evaluate_match,
    evaluate_rules,
    evaluate_switch,
)
from shared_core.workflow.context import WorkflowContext, new_execution_id
from shared_core.workflow.dag import detect_cycle, execution_plan, topological_order, validate_dag
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.exceptions import (
    CycleDetectedError,
    ExpressionEvaluationError,
    NodeNotFoundError,
)
from shared_core.workflow.expressions import evaluate_condition, evaluate_expression
from shared_core.workflow.graph import WorkflowGraph
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.variables import Variable, VariableScope, VariableStore

# --- variables.py ---


def test_variable_repr_masks_secret_scope() -> None:
    variable = Variable(name="password", value="hunter2", scope=VariableScope.SECRET)

    assert "hunter2" not in repr(variable)
    assert "***" in repr(variable)


def test_variable_repr_shows_non_secret_values() -> None:
    variable = Variable(name="count", value=42, scope=VariableScope.RUNTIME)

    assert "42" in repr(variable)


def test_variable_store_set_and_get_within_a_scope() -> None:
    store = VariableStore()
    store.set("name", "ada", scope=VariableScope.WORKFLOW)

    assert store.get("name", scope=VariableScope.WORKFLOW) == "ada"


def test_variable_store_get_returns_default_when_missing() -> None:
    store = VariableStore()

    assert store.get("missing", default="fallback") == "fallback"


def test_variable_store_get_by_precedence_prefers_higher_scope() -> None:
    store = VariableStore()
    store.set("x", "system-value", scope=VariableScope.SYSTEM)
    store.set("x", "runtime-value", scope=VariableScope.RUNTIME)

    assert store.get("x") == "runtime-value"


def test_variable_store_has_checks_a_specific_scope() -> None:
    store = VariableStore()
    store.set("x", 1, scope=VariableScope.RUNTIME)

    assert store.has("x", scope=VariableScope.RUNTIME) is True
    assert store.has("x", scope=VariableScope.SECRET) is False


def test_variable_store_has_checks_any_scope() -> None:
    store = VariableStore()
    store.set("x", 1, scope=VariableScope.RUNTIME)

    assert store.has("x") is True
    assert store.has("missing") is False


def test_variable_store_as_dict_masks_secrets_by_default() -> None:
    store = VariableStore()
    store.set("password", "hunter2", scope=VariableScope.SECRET)

    flattened = store.as_dict()

    assert flattened["password"] == "***"


def test_variable_store_as_dict_reveals_secrets_when_requested() -> None:
    store = VariableStore()
    store.set("password", "hunter2", scope=VariableScope.SECRET)

    flattened = store.as_dict(include_secrets=True)

    assert flattened["password"] == "hunter2"


def test_variable_store_child_is_independent() -> None:
    store = VariableStore()
    store.set("x", 1, scope=VariableScope.RUNTIME)
    child = store.child()

    child.set("x", 2, scope=VariableScope.RUNTIME)

    assert store.get("x") == 1
    assert child.get("x") == 2


def test_variable_scope_covers_every_documented_scope() -> None:
    expected = {"workflow", "environment", "runtime", "secret", "system", "context"}
    assert {scope.value for scope in VariableScope} == expected


# --- context.py ---


def test_new_execution_id_generates_unique_ids() -> None:
    assert new_execution_id() != new_execution_id()


def test_workflow_context_defaults() -> None:
    context = WorkflowContext(workflow_id="wf-1")

    assert context.execution_id
    assert context.variables.get("missing") is None


def test_workflow_context_child_has_independent_variables() -> None:
    parent = WorkflowContext(workflow_id="wf-1")
    parent.variables.set("x", 1, scope=VariableScope.RUNTIME)

    child = parent.child(node_id="node-1")
    child.variables.set("x", 2, scope=VariableScope.RUNTIME)

    assert parent.variables.get("x") == 1
    assert child.variables.get("x") == 2


def test_workflow_context_child_inherits_identity_fields() -> None:
    parent = WorkflowContext(
        workflow_id="wf-1", user_id="user-1", organization_id="org-1", project_id="proj-1"
    )

    child = parent.child(node_id="node-1")

    assert child.workflow_id == "wf-1"
    assert child.user_id == "user-1"
    assert child.organization_id == "org-1"
    assert child.project_id == "proj-1"
    assert child.execution_id == parent.execution_id


def test_workflow_context_child_extends_correlation_id() -> None:
    parent = WorkflowContext(workflow_id="wf-1", correlation_id="corr-1")

    child = parent.child(node_id="node-1")

    assert child.correlation_id == "corr-1:node-1"


def test_workflow_context_child_without_a_parent_correlation_id_uses_execution_id() -> None:
    parent = WorkflowContext(workflow_id="wf-1")

    child = parent.child(node_id="node-1")

    assert child.correlation_id == f"{parent.execution_id}:node-1"


# --- nodes.py ---


def test_node_type_covers_every_documented_type() -> None:
    expected = {
        "start",
        "end",
        "task",
        "connector",
        "plugin",
        "approval",
        "ai",
        "condition",
        "switch",
        "parallel",
        "merge",
        "loop",
        "delay",
        "timer",
        "sub_workflow",
        "webhook",
        "queue",
        "event",
        "script",
        "human_task",
    }
    assert {node_type.value for node_type in NodeType} == expected


def test_node_definition_defaults() -> None:
    node = NodeDefinition(node_id="n1", node_type=NodeType.TASK, name="do-thing")

    assert node.config == {}
    assert node.retryable is True


# --- expressions.py ---


def test_evaluate_expression_returns_the_computed_value() -> None:
    assert evaluate_expression("1 + 2", {}) == 3


def test_evaluate_expression_resolves_variables() -> None:
    assert evaluate_expression("count * 2", {"count": 5}) == 10


def test_evaluate_condition_coerces_to_bool() -> None:
    assert evaluate_condition("status == 'ok'", {"status": "ok"}) is True
    assert evaluate_condition("status == 'ok'", {"status": "bad"}) is False


def test_evaluate_expression_raises_for_a_malformed_expression() -> None:
    with pytest.raises(ExpressionEvaluationError):
        evaluate_expression("this is not valid ((", {})


def test_evaluate_expression_blocks_a_sandbox_escape() -> None:
    with pytest.raises(ExpressionEvaluationError):
        evaluate_expression("''.__class__.__mro__[1].__subclasses__()", {})


# --- conditions.py ---


def test_evaluate_if_else() -> None:
    assert evaluate_if_else("x > 0", {"x": 1}) is True


def test_evaluate_switch_returns_the_first_matching_case() -> None:
    cases = {"low": "x < 10", "high": "x >= 10"}

    assert evaluate_switch(cases, {"x": 20}) == "high"


def test_evaluate_switch_returns_default_when_nothing_matches() -> None:
    cases = {"low": "x < 10"}

    assert evaluate_switch(cases, {"x": 20}, default="none") == "none"


def test_evaluate_match_returns_the_matching_case() -> None:
    cases = {"a": "case-a", "b": "case-b"}

    assert evaluate_match("kind", cases, {"kind": "b"}) == "case-b"


def test_evaluate_match_returns_default_when_unmatched() -> None:
    cases = {"a": "case-a"}

    assert evaluate_match("kind", cases, {"kind": "z"}, default="fallback") == "fallback"


def test_evaluate_rules_returns_the_first_matching_rule() -> None:
    rules = [
        Rule(condition="x < 0", result="negative"),
        Rule(condition="x >= 0", result="non-negative"),
    ]

    assert evaluate_rules(rules, {"x": 5}) == "non-negative"


def test_evaluate_rules_returns_default_when_nothing_matches() -> None:
    rules = [Rule(condition="x < 0", result="negative")]

    assert evaluate_rules(rules, {"x": 5}, default="unknown") == "unknown"


# --- graph.py ---


def _linear_graph() -> WorkflowGraph:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
    graph.add_node(NodeDefinition(node_id="task", node_type=NodeType.TASK, name="task"))
    graph.add_node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
    graph.add_edge(EdgeDefinition(from_node_id="start", to_node_id="task"))
    graph.add_edge(EdgeDefinition(from_node_id="task", to_node_id="end"))
    return graph


def test_add_edge_rejects_an_unknown_node() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.START, name="a"))

    with pytest.raises(NodeNotFoundError):
        graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="missing"))


def test_get_node_raises_for_an_unknown_node() -> None:
    graph = WorkflowGraph()

    with pytest.raises(NodeNotFoundError):
        graph.get_node("missing")


def test_successors_and_predecessors() -> None:
    graph = _linear_graph()

    assert [edge.to_node_id for edge in graph.successors("start")] == ["task"]
    assert [edge.from_node_id for edge in graph.predecessors("end")] == ["task"]


def test_nodes_by_type() -> None:
    graph = _linear_graph()

    assert [node.node_id for node in graph.nodes_by_type(NodeType.TASK)] == ["task"]


# --- dag.py ---


def test_detect_cycle_none_for_an_acyclic_graph() -> None:
    graph = _linear_graph()

    assert detect_cycle(graph) is None


def test_detect_cycle_finds_a_direct_cycle() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.TASK, name="a"))
    graph.add_node(NodeDefinition(node_id="b", node_type=NodeType.TASK, name="b"))
    graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="b"))
    graph.add_edge(EdgeDefinition(from_node_id="b", to_node_id="a"))

    cycle = detect_cycle(graph)

    assert cycle is not None
    assert "a" in cycle and "b" in cycle


def test_validate_dag_passes_for_an_acyclic_graph() -> None:
    validate_dag(_linear_graph())


def test_validate_dag_raises_for_a_cyclic_graph() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.TASK, name="a"))
    graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="a"))

    with pytest.raises(CycleDetectedError):
        validate_dag(graph)


def test_topological_order_respects_dependencies() -> None:
    graph = _linear_graph()

    order = topological_order(graph)

    assert order.index("start") < order.index("task") < order.index("end")


def test_topological_order_raises_for_a_cycle() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.TASK, name="a"))
    graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="a"))

    with pytest.raises(CycleDetectedError):
        topological_order(graph)


def test_execution_plan_groups_independent_nodes_into_one_level() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.TASK, name="a"))
    graph.add_node(NodeDefinition(node_id="b", node_type=NodeType.TASK, name="b"))
    graph.add_node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
    graph.add_edge(EdgeDefinition(from_node_id="start", to_node_id="a"))
    graph.add_edge(EdgeDefinition(from_node_id="start", to_node_id="b"))
    graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="end"))
    graph.add_edge(EdgeDefinition(from_node_id="b", to_node_id="end"))

    plan = execution_plan(graph)

    assert plan == [["start"], ["a", "b"], ["end"]]


def test_execution_plan_raises_for_a_cycle() -> None:
    graph = WorkflowGraph()
    graph.add_node(NodeDefinition(node_id="a", node_type=NodeType.TASK, name="a"))
    graph.add_edge(EdgeDefinition(from_node_id="a", to_node_id="a"))

    with pytest.raises(CycleDetectedError):
        execution_plan(graph)


# --- definition.py ---


def test_workflow_definition_holds_nodes_and_edges() -> None:
    definition = WorkflowDefinition(
        workflow_id="wf-1",
        name="Sample",
        version="1.0.0",
        nodes=(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"),),
        edges=(),
    )

    assert definition.workflow_id == "wf-1"
    assert len(definition.nodes) == 1
    assert definition.default_variables == {}
