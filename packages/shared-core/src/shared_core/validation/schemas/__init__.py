"""Validation-framework schemas.

Structural models the rule functions in ``shared_core.validation.rules``
consume (a workflow graph's nodes/edges, a connector's config shape) --
not exposed API request/response schemas (docs/016 "DO NOT IMPLEMENT":
"REST APIs").
"""

from __future__ import annotations

from pydantic import Field

from shared_core.schemas.base import BaseSchema


class WorkflowNodeSchema(BaseSchema):
    """A single node in a workflow graph, for ``rules.workflow`` validators."""

    id: str
    type: str
    max_iterations: int | None = None
    required_inputs: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = None
    is_destructive: bool = False
    supports_rollback: bool = False


class WorkflowEdgeSchema(BaseSchema):
    """A directed edge between two workflow nodes."""

    source: str
    target: str


class ConnectorConfigSchema(BaseSchema):
    """Common connector configuration fields every connector type shares."""

    host: str
    timeout_seconds: int = 30
    version: str
    capabilities: list[str] = Field(default_factory=list)
    certificate: str | None = None
