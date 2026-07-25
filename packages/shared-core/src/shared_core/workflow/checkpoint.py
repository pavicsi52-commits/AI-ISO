"""Workflow checkpoints.

Per docs/028_Enterprise_Workflow_SDK.md.txt "CHECKPOINTS": Automatic,
Manual, Resume, Restore, Persistent Storage, Crash Recovery. Purely
in-process (:class:`CheckpointStore`) -- the same "no business tables"
stance as every prior framework's own state (e.g.
:class:`shared_core.scheduler.history.HistoryStore`); "Persistent
Storage" in a running service is whatever repository layer wraps this
store, not something this SDK creates a database table for itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shared_core.workflow.exceptions import CheckpointError
from shared_core.workflow.state_machine import WorkflowState


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A point-in-time snapshot of one workflow execution, enough to resume from."""

    execution_id: str
    state: WorkflowState
    completed_node_ids: tuple[str, ...]
    variables_snapshot: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    manual: bool = False


class CheckpointStore:
    """An in-process store of the most recent checkpoint per execution."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    def save(self, checkpoint: Checkpoint) -> None:
        """Save *checkpoint*, replacing any prior one for its execution ("Automatic"/"Manual")."""
        self._checkpoints[checkpoint.execution_id] = checkpoint

    def restore(self, execution_id: str) -> Checkpoint:
        """Retrieve the most recent checkpoint for *execution_id* ("Restore"/"Resume").

        Raises:
            CheckpointError: If no checkpoint exists for *execution_id*.
        """
        try:
            return self._checkpoints[execution_id]
        except KeyError as exc:
            raise CheckpointError(f"No checkpoint exists for execution {execution_id!r}.") from exc

    def has_checkpoint(self, execution_id: str) -> bool:
        """Whether a checkpoint exists for *execution_id* ("Crash Recovery")."""
        return execution_id in self._checkpoints

    def discard(self, execution_id: str) -> None:
        """Remove *execution_id*'s checkpoint. A no-op if none exists."""
        self._checkpoints.pop(execution_id, None)


__all__ = ["Checkpoint", "CheckpointStore"]
