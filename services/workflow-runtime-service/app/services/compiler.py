"""Translation between this service's own persisted
:class:`~app.models.workflow_version.WorkflowVersion` rows and
``shared_core.workflow``'s own in-memory DAG shapes.

The SDK's :func:`~shared_core.workflow.parser.parse_dict` expects an
edge mapping keyed ``"from"``/``"to"`` -- this service's own
:class:`~app.schemas.workflow.EdgeSchema`/DB row uses
``from_node_id``/``to_node_id`` instead (matching
``shared_core.workflow.edges.EdgeDefinition``'s own field names, which
``parse_dict`` itself does NOT use for its raw dict input shape) --
this module is the one place that bridges the two.
"""

from __future__ import annotations

from typing import Any

from shared_core.workflow import CompiledWorkflow, WorkflowDefinition, compile_workflow, parse_dict

from app.models.workflow_definition import WorkflowDefinition as WorkflowDefinitionModel
from app.models.workflow_version import WorkflowVersion as WorkflowVersionModel


def nodes_to_dicts(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pass node dicts through unchanged -- ``parse_dict`` already
    expects this service's own node shape verbatim.
    """
    return nodes


def edges_to_sdk_dicts(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate this service's own ``from_node_id``/``to_node_id`` edge
    shape into the SDK parser's own ``"from"``/``"to"`` keys.
    """
    translated: list[dict[str, Any]] = []
    for edge in edges:
        entry: dict[str, Any] = {"from": edge["from_node_id"], "to": edge["to_node_id"]}
        if edge.get("condition") is not None:
            entry["condition"] = edge["condition"]
        if edge.get("label") is not None:
            entry["label"] = edge["label"]
        translated.append(entry)
    return translated


def to_sdk_definition(
    definition: WorkflowDefinitionModel, version: WorkflowVersionModel
) -> WorkflowDefinition:
    """Reconstruct *version*'s own DAG as a real
    ``shared_core.workflow.WorkflowDefinition`` the SDK can compile/run.
    """
    return parse_dict(
        {
            "workflow_id": definition.workflow_key,
            "name": definition.name,
            "version": version.version_number,
            "description": definition.description,
            "owner": definition.owner,
            "tags": list(definition.tags),
            "variables": dict(definition.default_variables),
            "nodes": nodes_to_dicts(version.nodes),
            "edges": edges_to_sdk_dicts(version.edges),
        }
    )


def compile_version(
    definition: WorkflowDefinitionModel, version: WorkflowVersionModel
) -> CompiledWorkflow:
    """Compile *version*'s own DAG, raising
    :class:`~shared_core.workflow.exceptions.InvalidWorkflowDefinitionError`/
    :class:`~shared_core.workflow.exceptions.CycleDetectedError` if it's
    structurally invalid ("Cycle Detection").
    """
    return compile_workflow(to_sdk_definition(definition, version))


__all__ = ["compile_version", "edges_to_sdk_dicts", "nodes_to_dicts", "to_sdk_definition"]
