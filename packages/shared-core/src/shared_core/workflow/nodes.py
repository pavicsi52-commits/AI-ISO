"""Workflow node definitions.

Per docs/028_Enterprise_Workflow_SDK.md.txt "NODE TYPES": Start, End,
Task, Connector, Plugin, Approval, AI, Condition, Switch, Parallel,
Merge, Loop, Delay, Timer, Sub Workflow, Webhook, Queue, Event, Script,
Human Task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from shared_core.workflow.constants import DEFAULT_TASK_TIMEOUT_SECONDS


class NodeType(StrEnum):
    """Every node type docs/028 "NODE TYPES" names."""

    START = "start"
    END = "end"
    TASK = "task"
    CONNECTOR = "connector"
    PLUGIN = "plugin"
    APPROVAL = "approval"
    AI = "ai"
    CONDITION = "condition"
    SWITCH = "switch"
    PARALLEL = "parallel"
    MERGE = "merge"
    LOOP = "loop"
    DELAY = "delay"
    TIMER = "timer"
    SUB_WORKFLOW = "sub_workflow"
    WEBHOOK = "webhook"
    QUEUE = "queue"
    EVENT = "event"
    SCRIPT = "script"
    HUMAN_TASK = "human_task"


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    """One node in a workflow's graph.

    ``config`` holds every node-type-specific parameter (a ``TASK``
    node's registered handler name, a ``CONNECTOR`` node's provider/
    operation, a ``CONDITION``/``SWITCH`` node's expression, a ``LOOP``
    node's max iterations, a ``DELAY``/``TIMER`` node's duration, a
    ``SUB_WORKFLOW`` node's target workflow id, ...) -- kept as a
    generic mapping rather than one dataclass field per node type,
    since which fields apply depends entirely on *node_type*.
    """

    node_id: str
    node_type: NodeType
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TASK_TIMEOUT_SECONDS
    retryable: bool = True


__all__ = ["NodeDefinition", "NodeType"]
