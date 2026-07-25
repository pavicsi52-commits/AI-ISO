"""Workflow rollback.

Per docs/028_Enterprise_Workflow_SDK.md.txt "ROLLBACK": Automatic
Rollback, Manual Rollback, Partial Rollback, Compensation Actions,
State Restoration. Implements the Saga pattern on top of
:class:`shared_core.workflow.compensation.CompensationRegistry`: undo
every completed node in reverse completion order, so a workflow that
fails partway through can unwind whatever it already did.
"""

from __future__ import annotations

from shared_core.workflow.compensation import CompensationRegistry
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import RollbackError
from shared_core.workflow.execution import WorkflowExecution
from shared_core.workflow.state_machine import WorkflowState


async def rollback_workflow(
    execution: WorkflowExecution,
    compensations: CompensationRegistry,
    context: WorkflowContext,
    *,
    node_ids: list[str] | None = None,
) -> list[str]:
    """Undo completed nodes in reverse completion order ("Automatic Rollback"/"Partial Rollback").

    *node_ids*, if given, restricts rollback to just those nodes
    ("Partial Rollback"/"Manual Rollback" -- a caller decides exactly
    which completed steps to undo) rather than every completed node.

    Returns the node ids actually compensated, in the order they were
    compensated ("State Restoration" undoes the most recently
    completed node first, the same as any undo stack).

    Raises:
        RollbackError: If a compensation action fails; nodes already
            compensated before the failure stay compensated (rollback
            doesn't retry or roll itself back).
    """
    target_ids = set(node_ids) if node_ids is not None else set(execution.completed_node_ids())
    all_node_ids = reversed(list(execution.node_results))
    ordered = [node_id for node_id in all_node_ids if node_id in target_ids]

    compensated: list[str] = []
    for node_id in ordered:
        if not compensations.has_compensation(node_id):
            continue
        try:
            await compensations.execute(node_id, context)
        except Exception as exc:
            raise RollbackError(
                f"Rollback failed at node {node_id!r} after compensating {compensated}: {exc}"
            ) from exc
        compensated.append(node_id)
        execution.node_results[node_id].status = WorkflowState.ROLLED_BACK
    return compensated


__all__ = ["rollback_workflow"]
