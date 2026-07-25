"""Workflow event integration.

Per docs/028_Enterprise_Workflow_SDK.md.txt "EVENT INTEGRATION":
Workflow Started, Task Started, Task Completed, Task Failed, Workflow
Completed, Workflow Failed, Workflow Cancelled, Workflow Rolled Back.
"Integrate with Prompt 020." Reuses
:class:`shared_core.events.base.BaseEvent` directly (already
implements the full event envelope: id, tenant/correlation fields,
timestamp, payload) rather than a second event model --
``EventType.WORKFLOW`` was already anticipated in Prompt 020's baseline
``EventType`` enum.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events.base import BaseEvent, EventType


class WorkflowEvent(BaseEvent):
    """Base class every workflow lifecycle event inherits."""

    event_type: ClassVar[EventType] = EventType.WORKFLOW


class WorkflowStartedEvent(WorkflowEvent):
    """A workflow execution began ("Workflow Started")."""

    event_name: ClassVar[str] = "workflow.started"


class WorkflowCompletedEvent(WorkflowEvent):
    """A workflow execution finished successfully ("Workflow Completed")."""

    event_name: ClassVar[str] = "workflow.completed"


class WorkflowFailedEvent(WorkflowEvent):
    """A workflow execution failed ("Workflow Failed")."""

    event_name: ClassVar[str] = "workflow.failed"


class WorkflowCancelledEvent(WorkflowEvent):
    """A workflow execution was cancelled ("Workflow Cancelled")."""

    event_name: ClassVar[str] = "workflow.cancelled"


class WorkflowRolledBackEvent(WorkflowEvent):
    """A workflow execution was rolled back ("Workflow Rolled Back")."""

    event_name: ClassVar[str] = "workflow.rolled_back"


class TaskStartedEvent(WorkflowEvent):
    """One node's task began ("Task Started")."""

    event_name: ClassVar[str] = "workflow.task.started"


class TaskCompletedEvent(WorkflowEvent):
    """One node's task finished successfully ("Task Completed")."""

    event_name: ClassVar[str] = "workflow.task.completed"


class TaskFailedEvent(WorkflowEvent):
    """One node's task failed ("Task Failed")."""

    event_name: ClassVar[str] = "workflow.task.failed"


def build_workflow_event(
    event_cls: type[WorkflowEvent],
    *,
    source_service: str,
    execution_id: str,
    workflow_id: str,
    node_id: str | None = None,
    **extra_payload: object,
) -> WorkflowEvent:
    """Build one of this module's event classes with a consistent payload shape."""
    payload: dict[str, object] = {"execution_id": execution_id, "workflow_id": workflow_id}
    if node_id is not None:
        payload["node_id"] = node_id
    payload.update(extra_payload)
    return event_cls(source_service=source_service, payload=payload)


__all__ = [
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "TaskStartedEvent",
    "WorkflowCancelledEvent",
    "WorkflowCompletedEvent",
    "WorkflowEvent",
    "WorkflowFailedEvent",
    "WorkflowRolledBackEvent",
    "WorkflowStartedEvent",
    "build_workflow_event",
]
