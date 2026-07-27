"""Translation between this service's own persisted
:class:`~app.models.enums.WorkflowInstanceStatus` (docs/042's own
12-value verbatim "STATE MACHINE" list) and
``shared_core.workflow.WorkflowState`` (the SDK's own distinct 11-value
set) -- see ``app/models/enums.py``'s own docstring for why these are
never the same enum. ``CHECKPOINTED`` has no SDK equivalent (it is a
DB-only overlay this service applies the moment a checkpoint is
persisted, before the SDK's own next state transition supersedes it);
``QUEUED``/``PENDING`` are the same concept under each side's own name.
"""

from __future__ import annotations

from shared_core.workflow import WorkflowState

from app.models.enums import WorkflowInstanceStatus

_SDK_TO_INSTANCE: dict[WorkflowState, WorkflowInstanceStatus] = {
    WorkflowState.CREATED: WorkflowInstanceStatus.CREATED,
    WorkflowState.PENDING: WorkflowInstanceStatus.QUEUED,
    WorkflowState.RUNNING: WorkflowInstanceStatus.RUNNING,
    WorkflowState.PAUSED: WorkflowInstanceStatus.PAUSED,
    WorkflowState.WAITING: WorkflowInstanceStatus.WAITING,
    WorkflowState.RETRYING: WorkflowInstanceStatus.RETRYING,
    WorkflowState.COMPLETED: WorkflowInstanceStatus.COMPLETED,
    WorkflowState.CANCELLED: WorkflowInstanceStatus.CANCELLED,
    WorkflowState.FAILED: WorkflowInstanceStatus.FAILED,
    WorkflowState.ROLLED_BACK: WorkflowInstanceStatus.ROLLED_BACK,
    WorkflowState.ARCHIVED: WorkflowInstanceStatus.ARCHIVED,
}

_INSTANCE_TO_SDK: dict[WorkflowInstanceStatus, WorkflowState] = {
    WorkflowInstanceStatus.CREATED: WorkflowState.CREATED,
    WorkflowInstanceStatus.QUEUED: WorkflowState.PENDING,
    WorkflowInstanceStatus.WAITING: WorkflowState.WAITING,
    WorkflowInstanceStatus.RUNNING: WorkflowState.RUNNING,
    WorkflowInstanceStatus.PAUSED: WorkflowState.PAUSED,
    WorkflowInstanceStatus.CHECKPOINTED: WorkflowState.RUNNING,
    WorkflowInstanceStatus.RETRYING: WorkflowState.RETRYING,
    WorkflowInstanceStatus.COMPLETED: WorkflowState.COMPLETED,
    WorkflowInstanceStatus.CANCELLED: WorkflowState.CANCELLED,
    WorkflowInstanceStatus.FAILED: WorkflowState.FAILED,
    WorkflowInstanceStatus.ROLLED_BACK: WorkflowState.ROLLED_BACK,
    WorkflowInstanceStatus.ARCHIVED: WorkflowState.ARCHIVED,
}


def from_sdk_state(state: WorkflowState) -> WorkflowInstanceStatus:
    """Translate an SDK ``WorkflowState`` into this service's own persisted status."""
    return _SDK_TO_INSTANCE[state]


def to_sdk_state(status: WorkflowInstanceStatus) -> WorkflowState:
    """Translate this service's own persisted status into an SDK ``WorkflowState``."""
    return _INSTANCE_TO_SDK[status]


__all__ = ["from_sdk_state", "to_sdk_state"]
