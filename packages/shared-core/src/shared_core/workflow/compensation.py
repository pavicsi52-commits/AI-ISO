"""Compensation actions.

Per docs/028_Enterprise_Workflow_SDK.md.txt "COMPENSATION": Register
Compensation, Execute Compensation, Reverse Operations, Failure
Recovery, Saga Pattern Support. A :class:`CompensationRegistry` maps a
node id to the async callable that reverses its effect --
:mod:`shared_core.workflow.rollback` walks these in reverse completion
order to implement the Saga pattern (undo already-completed steps when
a later step fails).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import CompensationError

CompensationAction = Callable[[WorkflowContext], Awaitable[None]]


class CompensationRegistry:
    """Maps node id -> its compensation ("undo") action ("Register Compensation")."""

    def __init__(self) -> None:
        self._actions: dict[str, CompensationAction] = {}

    def register(self, node_id: str, action: CompensationAction) -> None:
        """Register *action* as *node_id*'s compensation ("Reverse Operations")."""
        self._actions[node_id] = action

    def has_compensation(self, node_id: str) -> bool:
        """Whether *node_id* has a registered compensation action."""
        return node_id in self._actions

    async def execute(self, node_id: str, context: WorkflowContext) -> None:
        """Run *node_id*'s compensation action, if registered ("Execute Compensation").

        A no-op if no action is registered -- not every completed node
        needs a real compensation (e.g. a read-only ``TASK``).

        Raises:
            CompensationError: If the registered action itself raises.
        """
        action = self._actions.get(node_id)
        if action is None:
            return
        try:
            await action(context)
        except Exception as exc:
            raise CompensationError(f"Compensation for node {node_id!r} failed: {exc}") from exc


__all__ = ["CompensationAction", "CompensationRegistry"]
