"""Workflow definition parsing.

Per docs/028_Enterprise_Workflow_SDK.md.txt "WORKFLOW DEFINITION":
Support YAML, JSON, Python DSL, Future Visual Designer. YAML/JSON both
funnel through :func:`parse_dict` (one shared shape both formats decode
into); :class:`WorkflowBuilder` is the Python DSL -- a fluent,
code-first way to build a
:class:`~shared_core.workflow.definition.WorkflowDefinition` without
hand-writing a nodes/edges dict.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from shared_core.workflow.constants import DEFAULT_TASK_TIMEOUT_SECONDS
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.exceptions import InvalidWorkflowDefinitionError
from shared_core.workflow.nodes import NodeDefinition, NodeType


def _parse_node(raw: dict[str, Any]) -> NodeDefinition:
    return NodeDefinition(
        node_id=raw["node_id"],
        node_type=NodeType(raw["node_type"]),
        name=raw.get("name", raw["node_id"]),
        config=dict(raw.get("config", {})),
        timeout_seconds=float(raw.get("timeout_seconds", DEFAULT_TASK_TIMEOUT_SECONDS)),
        retryable=bool(raw.get("retryable", True)),
    )


def _parse_edge(raw: dict[str, Any]) -> EdgeDefinition:
    return EdgeDefinition(
        from_node_id=raw["from"],
        to_node_id=raw["to"],
        condition=raw.get("condition"),
        label=raw.get("label"),
    )


def parse_dict(data: dict[str, Any]) -> WorkflowDefinition:
    """Parse a plain dict (already decoded from YAML/JSON) into a ``WorkflowDefinition``.

    Raises:
        InvalidWorkflowDefinitionError: If a required field is missing
            or malformed.
    """
    try:
        nodes = tuple(_parse_node(raw) for raw in data["nodes"])
        edges = tuple(_parse_edge(raw) for raw in data.get("edges", []))
        return WorkflowDefinition(
            workflow_id=data["workflow_id"],
            name=data["name"],
            version=data["version"],
            nodes=nodes,
            edges=edges,
            description=data.get("description"),
            default_variables=dict(data.get("variables", {})),
            tags=tuple(data.get("tags", ())),
            owner=data.get("owner"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidWorkflowDefinitionError(f"Malformed workflow definition: {exc}") from exc


def parse_yaml(text: str) -> WorkflowDefinition:
    """Parse a YAML workflow definition ("YAML").

    Raises:
        InvalidWorkflowDefinitionError: If *text* isn't valid YAML, or
            the decoded structure is malformed.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidWorkflowDefinitionError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidWorkflowDefinitionError("A workflow definition must decode to a mapping.")
    return parse_dict(data)


def parse_json(text: str) -> WorkflowDefinition:
    """Parse a JSON workflow definition ("JSON").

    Raises:
        InvalidWorkflowDefinitionError: If *text* isn't valid JSON, or
            the decoded structure is malformed.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidWorkflowDefinitionError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidWorkflowDefinitionError("A workflow definition must decode to a mapping.")
    return parse_dict(data)


class WorkflowBuilder:
    """A fluent, code-first way to build a ``WorkflowDefinition`` ("Python DSL")."""

    def __init__(self, workflow_id: str, name: str, *, version: str = "1.0.0") -> None:
        self._workflow_id = workflow_id
        self._name = name
        self._version = version
        self._description: str | None = None
        self._nodes: list[NodeDefinition] = []
        self._edges: list[EdgeDefinition] = []
        self._default_variables: dict[str, Any] = {}
        self._tags: list[str] = []
        self._owner: str | None = None

    def description(self, text: str) -> WorkflowBuilder:
        """Set the workflow's description. Returns ``self`` for chaining."""
        self._description = text
        return self

    def owner(self, owner: str) -> WorkflowBuilder:
        """Set the workflow's owner. Returns ``self`` for chaining."""
        self._owner = owner
        return self

    def tag(self, *tags: str) -> WorkflowBuilder:
        """Add one or more tags. Returns ``self`` for chaining."""
        self._tags.extend(tags)
        return self

    def variable(self, name: str, value: Any) -> WorkflowBuilder:
        """Set a default workflow variable. Returns ``self`` for chaining."""
        self._default_variables[name] = value
        return self

    def node(self, node: NodeDefinition) -> WorkflowBuilder:
        """Add a node. Returns ``self`` for chaining."""
        self._nodes.append(node)
        return self

    def edge(self, edge: EdgeDefinition) -> WorkflowBuilder:
        """Add an edge. Returns ``self`` for chaining."""
        self._edges.append(edge)
        return self

    def build(self) -> WorkflowDefinition:
        """Build the final, immutable ``WorkflowDefinition``."""
        return WorkflowDefinition(
            workflow_id=self._workflow_id,
            name=self._name,
            version=self._version,
            nodes=tuple(self._nodes),
            edges=tuple(self._edges),
            description=self._description,
            default_variables=dict(self._default_variables),
            tags=tuple(self._tags),
            owner=self._owner,
        )


__all__ = ["WorkflowBuilder", "parse_dict", "parse_json", "parse_yaml"]
