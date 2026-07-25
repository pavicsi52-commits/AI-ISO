"""Workflow definition.

Per docs/028_Enterprise_Workflow_SDK.md.txt "WORKFLOW DEFINITION":
Support YAML, JSON, Python DSL, Future Visual Designer; "Validate every
workflow before execution." Per "WORKFLOW PRINCIPLES": "Every workflow
is versioned." A :class:`WorkflowDefinition` is the static, versioned
description of a workflow's graph -- parsing
(:mod:`~shared_core.workflow.parser`), validation
(:mod:`~shared_core.workflow.validator`), and compiling into a runnable
:class:`~shared_core.workflow.graph.WorkflowGraph`
(:mod:`~shared_core.workflow.compiler`) all operate on this model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.nodes import NodeDefinition


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """The static, versioned description of one workflow ("Every workflow is versioned")."""

    workflow_id: str
    name: str
    version: str
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    description: str | None = None
    default_variables: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    owner: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


__all__ = ["WorkflowDefinition"]
