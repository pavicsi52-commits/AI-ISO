"""Durable checkpoint persistence. Per docs/042 "CHECKPOINTING"
"Support": Automatic Checkpoints, Manual Checkpoints, Resume, Restore,
Persistent State, Crash Recovery, Distributed Recovery.

:class:`~shared_core.workflow.checkpoint.CheckpointStore` is a plain
in-memory ``dict`` with no persistence of its own (confirmed: not an
ABC, nothing in the SDK subclasses it, and the engine calls
``save()``/``restore()`` synchronously, never awaited). Real DB I/O
inside that synchronous call site would either block the event loop or
require a fire-and-forget task with no error visibility -- instead,
:class:`PersistentCheckpointStore` keeps the engine's own in-memory
behavior via ``super().save()`` (so ``restore()``/``has_checkpoint()``
still work exactly as the engine expects mid-run) and additionally
buffers every checkpoint in a plain list; ``app/services/execution.py``
drains that buffer with :meth:`PersistentCheckpointStore.drain_pending`
and persists each one through :class:`WorkflowCheckpointService` once
back in an ``async`` context, immediately after ``await engine.run(...)``
returns.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.workflow import Checkpoint, CheckpointStore

from app.models.enums import CheckpointType
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.services.status import from_sdk_state


class PersistentCheckpointStore(CheckpointStore):
    """A :class:`CheckpointStore` that also buffers every checkpoint for
    later durable persistence.
    """

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


class WorkflowCheckpointService:
    """Persists and reads durable workflow checkpoints."""

    def __init__(self, checkpoints: WorkflowCheckpointRepository) -> None:
        self._checkpoints = checkpoints

    async def persist(
        self,
        *,
        organization_id: UUID,
        instance_id: UUID,
        checkpoint: Checkpoint,
        checkpoint_type: CheckpointType = CheckpointType.AUTOMATIC,
    ) -> WorkflowCheckpoint:
        """Durably record one SDK ``Checkpoint`` for *instance_id*."""
        return await self._checkpoints.create(
            WorkflowCheckpoint(
                organization_id=organization_id,
                instance_id=instance_id,
                checkpoint_type=checkpoint_type,
                state=from_sdk_state(checkpoint.state),
                completed_node_ids=list(checkpoint.completed_node_ids),
                variables_snapshot=dict(checkpoint.variables_snapshot),
                checkpointed_at=checkpoint.created_at,
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowCheckpoint]:
        """Every checkpoint recorded for *instance_id*, newest first."""
        return await self._checkpoints.list_for_instance(instance_id)

    async def get_latest_for_instance(self, instance_id: UUID) -> WorkflowCheckpoint | None:
        """Return *instance_id*'s most recently recorded checkpoint, or ``None``."""
        return await self._checkpoints.get_latest_for_instance(instance_id)


__all__ = ["PersistentCheckpointStore", "WorkflowCheckpointService"]
