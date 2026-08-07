"""Translation between this service's own persisted
:class:`~app.models.enums.WorkflowRunStatus` (six values) and
``shared_core.workflow.WorkflowState`` (the SDK's own distinct eleven-
value set) -- mirrors ``workflow-runtime-service``'s own ``app/services
/status.py`` shape, squeezed to this service's own coarser vocabulary.

Several SDK states have no distinct equivalent here and fold onto the
nearest one: ``CREATED``/``WAITING``/``RETRYING`` all read as
``RUNNING`` (this service tracks "in progress" at one granularity, not
the SDK's own finer sub-states), and ``ROLLED_BACK``/``ARCHIVED`` fold
onto ``FAILED``/``COMPLETED`` respectively.
"""

from __future__ import annotations

from shared_core.workflow import WorkflowState

from app.models.enums import WorkflowRunStatus

_SDK_TO_RUN_STATUS: dict[WorkflowState, WorkflowRunStatus] = {
    WorkflowState.CREATED: WorkflowRunStatus.PENDING,
    WorkflowState.PENDING: WorkflowRunStatus.PENDING,
    WorkflowState.RUNNING: WorkflowRunStatus.RUNNING,
    WorkflowState.PAUSED: WorkflowRunStatus.PAUSED_FOR_APPROVAL,
    WorkflowState.WAITING: WorkflowRunStatus.RUNNING,
    WorkflowState.RETRYING: WorkflowRunStatus.RUNNING,
    WorkflowState.COMPLETED: WorkflowRunStatus.COMPLETED,
    WorkflowState.CANCELLED: WorkflowRunStatus.CANCELLED,
    WorkflowState.FAILED: WorkflowRunStatus.FAILED,
    WorkflowState.ROLLED_BACK: WorkflowRunStatus.FAILED,
    WorkflowState.ARCHIVED: WorkflowRunStatus.COMPLETED,
}

_RUN_STATUS_TO_SDK: dict[WorkflowRunStatus, WorkflowState] = {
    WorkflowRunStatus.PENDING: WorkflowState.PENDING,
    WorkflowRunStatus.RUNNING: WorkflowState.RUNNING,
    WorkflowRunStatus.PAUSED_FOR_APPROVAL: WorkflowState.PAUSED,
    WorkflowRunStatus.COMPLETED: WorkflowState.COMPLETED,
    WorkflowRunStatus.FAILED: WorkflowState.FAILED,
    WorkflowRunStatus.CANCELLED: WorkflowState.CANCELLED,
}


def from_sdk_state(state: WorkflowState) -> WorkflowRunStatus:
    """Translate an SDK ``WorkflowState`` into this service's own persisted status."""
    if not isinstance(state, WorkflowState):
        state = WorkflowState(state)
    return _SDK_TO_RUN_STATUS[state]


def to_sdk_state(status: WorkflowRunStatus) -> WorkflowState:
    """Translate this service's own persisted status into an SDK ``WorkflowState``."""
    if not isinstance(status, WorkflowRunStatus):
        status = WorkflowRunStatus(status)
    return _RUN_STATUS_TO_SDK[status]


__all__ = ["from_sdk_state", "to_sdk_state"]
