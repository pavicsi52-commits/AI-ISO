"""Durable checkpoint persistence (docs/060's own "LangGraph-style
workflow persistence" note on :class:`~app.models.workflow
.AgentWorkflow`).

:class:`~shared_core.workflow.checkpoint.CheckpointStore` is a plain
in-memory ``dict`` with no persistence of its own -- confirmed by its
own docstring: "'Persistent Storage' in a running service is whatever
repository layer wraps this store." Mirrors ``workflow-runtime-
service``'s own ``app/services/checkpoint.PersistentCheckpointStore``:
keeps the engine's own in-memory behavior via ``super().save()`` (so
``restore()``/``has_checkpoint()`` still work exactly as the engine
expects mid-run, since the engine calls them synchronously, never
awaited) and additionally buffers every checkpoint in a plain list;
:class:`~app.langgraph.service.WorkflowPersistenceService` drains that
buffer and writes the latest one onto the owning
:class:`~app.models.workflow.AgentWorkflow` row once back in an
``async`` context, immediately after ``await engine.run(...)`` returns.

Unlike that precedent, there is no separate checkpoint history table
here -- ``AgentWorkflow.checkpoint`` holds only the single latest one,
matching docs/060's own compact 17-table design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.workflow import Checkpoint, CheckpointStore, WorkflowState


class PersistentCheckpointStore(CheckpointStore):
    """A :class:`CheckpointStore` that also buffers every checkpoint for
    later durable persistence."""

    def __init__(self) -> None:
        super().__init__()
        self._pending: list[Checkpoint] = []

    def save(self, checkpoint: Checkpoint) -> None:
        super().save(checkpoint)
        self._pending.append(checkpoint)

    def drain_pending(self) -> list[Checkpoint]:
        """Return and clear every checkpoint buffered since the last drain."""
        pending = self._pending
        self._pending = []
        return pending


def checkpoint_to_dict(checkpoint: Checkpoint) -> dict[str, Any]:
    """Serialise a :class:`Checkpoint` for storage in a JSON column."""
    return {
        "execution_id": checkpoint.execution_id,
        "state": str(checkpoint.state),
        "completed_node_ids": list(checkpoint.completed_node_ids),
        "variables_snapshot": dict(checkpoint.variables_snapshot),
        "created_at": checkpoint.created_at.isoformat(),
        "manual": checkpoint.manual,
    }


def checkpoint_from_dict(data: dict[str, Any]) -> Checkpoint:
    """Deserialise a previously stored checkpoint back into the SDK's
    own :class:`Checkpoint` shape, for resuming a paused/crashed run."""
    return Checkpoint(
        execution_id=data["execution_id"],
        state=WorkflowState(data["state"]),
        completed_node_ids=tuple(data.get("completed_node_ids", ())),
        variables_snapshot=dict(data.get("variables_snapshot", {})),
        created_at=datetime.fromisoformat(data["created_at"]),
        manual=bool(data.get("manual", False)),
    )


__all__ = ["PersistentCheckpointStore", "checkpoint_from_dict", "checkpoint_to_dict"]
