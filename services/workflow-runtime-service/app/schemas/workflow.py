"""Request/response schemas for ``/workflows``.

``NodeSchema``/``EdgeSchema`` mirror
``shared_core.workflow.nodes.NodeDefinition``/``edges.EdgeDefinition``'s
own field shapes (reusing ``shared_core.workflow.NodeType`` directly --
it is genuinely shared vocabulary, not a service-specific concept, see
``app/models/enums.py``'s own docstring) so a caller can define a DAG
using the exact same field names the SDK itself uses; ``app/services
/compiler.py`` translates ``EdgeSchema.from_node_id``/``to_node_id``
into the SDK parser's own ``"from"``/``"to"`` dict keys.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.workflow import DEFAULT_TASK_TIMEOUT_SECONDS, NodeType


class NodeSchema(BaseModel):
    """One DAG node, mirroring ``shared_core.workflow.nodes.NodeDefinition``."""

    node_id: str = Field(min_length=1, max_length=255)
    node_type: NodeType
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=DEFAULT_TASK_TIMEOUT_SECONDS, gt=0)
    retryable: bool = True


class EdgeSchema(BaseModel):
    """One DAG edge, mirroring ``shared_core.workflow.edges.EdgeDefinition``."""

    from_node_id: str = Field(min_length=1, max_length=255)
    to_node_id: str = Field(min_length=1, max_length=255)
    condition: str | None = None
    label: str | None = None


class WorkflowCreateRequest(BaseModel):
    """Body of ``POST /workflows`` -- defines a workflow and its own first DAG version."""

    organization_id: UUID
    project_id: UUID | None = None
    workflow_key: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)
    default_variables: dict[str, Any] = Field(default_factory=dict)
    nodes: list[NodeSchema] = Field(min_length=1)
    edges: list[EdgeSchema] = Field(default_factory=list)


class WorkflowUpdateRequest(BaseModel):
    """Body of ``PUT /workflows/{id}`` -- replaces metadata and always
    records a new DAG version ("Version" is implicit in every update,
    docs/042 names no separate versioning endpoint of its own).
    """

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)
    default_variables: dict[str, Any] = Field(default_factory=dict)
    nodes: list[NodeSchema] = Field(min_length=1)
    edges: list[EdgeSchema] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    """One reusable workflow definition."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    workflow_key: str
    name: str
    description: str | None
    owner: str | None
    tags: list[str]
    default_variables: dict[str, Any]
    current_version_number: str | None


class WorkflowVersionResponse(BaseModel):
    """One immutable DAG snapshot of a workflow definition."""

    id: UUID
    definition_id: UUID
    version_number: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    compiled_execution_plan: list[list[str]]


class WorkflowExecuteRequest(BaseModel):
    """Body of ``POST /workflows/{id}/execute``."""

    variables: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "EdgeSchema",
    "NodeSchema",
    "WorkflowCreateRequest",
    "WorkflowExecuteRequest",
    "WorkflowResponse",
    "WorkflowUpdateRequest",
    "WorkflowVersionResponse",
]
