"""Workflow state machine.

Per docs/028_Enterprise_Workflow_SDK.md.txt "STATE MACHINE": States
(Created, Pending, Running, Paused, Waiting, Retrying, Completed,
Cancelled, Failed, Rolled Back, Archived), "Support custom states."
"""

from __future__ import annotations

from enum import StrEnum

from shared_core.workflow.exceptions import InvalidStateTransitionError


class WorkflowState(StrEnum):
    """Every state docs/028 "STATE MACHINE" names."""

    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    RETRYING = "retrying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


_DEFAULT_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.CREATED: frozenset({WorkflowState.PENDING, WorkflowState.CANCELLED}),
    WorkflowState.PENDING: frozenset({WorkflowState.RUNNING, WorkflowState.CANCELLED}),
    WorkflowState.RUNNING: frozenset(
        {
            WorkflowState.PAUSED,
            WorkflowState.WAITING,
            WorkflowState.RETRYING,
            WorkflowState.COMPLETED,
            WorkflowState.FAILED,
            WorkflowState.CANCELLED,
        }
    ),
    WorkflowState.PAUSED: frozenset({WorkflowState.RUNNING, WorkflowState.CANCELLED}),
    WorkflowState.WAITING: frozenset(
        {WorkflowState.RUNNING, WorkflowState.CANCELLED, WorkflowState.FAILED}
    ),
    WorkflowState.RETRYING: frozenset(
        {WorkflowState.RUNNING, WorkflowState.FAILED, WorkflowState.CANCELLED}
    ),
    WorkflowState.COMPLETED: frozenset({WorkflowState.ARCHIVED}),
    WorkflowState.CANCELLED: frozenset({WorkflowState.ARCHIVED}),
    WorkflowState.FAILED: frozenset(
        {WorkflowState.ROLLED_BACK, WorkflowState.RETRYING, WorkflowState.ARCHIVED}
    ),
    WorkflowState.ROLLED_BACK: frozenset({WorkflowState.ARCHIVED}),
    WorkflowState.ARCHIVED: frozenset(),
}


class StateMachine:
    """Governs valid state transitions for one workflow execution.

    A caller-supplied *transitions* map lets a custom workflow
    substitute its own transition table entirely ("Support custom
    states") while still going through the same validated
    :meth:`transition` call.
    """

    def __init__(
        self,
        *,
        initial_state: WorkflowState = WorkflowState.CREATED,
        transitions: dict[WorkflowState, frozenset[WorkflowState]] | None = None,
    ) -> None:
        self._state = initial_state
        self._transitions = transitions if transitions is not None else _DEFAULT_TRANSITIONS
        self._history: list[WorkflowState] = [initial_state]

    @property
    def state(self) -> WorkflowState:
        """This machine's current state."""
        return self._state

    @property
    def history(self) -> list[WorkflowState]:
        """Every state this machine has been in, in order (including the current one)."""
        return list(self._history)

    def can_transition(self, target: WorkflowState) -> bool:
        """Whether moving from the current state to *target* is allowed."""
        return target in self._transitions.get(self._state, frozenset())

    def transition(self, target: WorkflowState) -> None:
        """Move to *target*.

        Raises:
            InvalidStateTransitionError: If not allowed from the current state.
        """
        if not self.can_transition(target):
            raise InvalidStateTransitionError(
                f"Cannot transition from {self._state.value!r} to {target.value!r}."
            )
        self._state = target
        self._history.append(target)

    def is_terminal(self) -> bool:
        """Whether the current state has no further transitions defined."""
        return not self._transitions.get(self._state, frozenset())


__all__ = ["StateMachine", "WorkflowState"]
