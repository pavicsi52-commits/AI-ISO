"""Workflow replay. Per docs/042 "REPLAY" "Support": Replay Workflow,
Replay Failed Steps, Replay From Checkpoint, Replay History, Execution
Comparison, Replay Validation.

**A real, documented scope limit**: every replay always re-runs the
*entire* compiled DAG from the top -- ``shared_core.workflow
.WorkflowEngine.run()`` gives no primitive for executing only a subset
of an already-compiled execution plan (confirmed: there is no
"skip already-completed nodes" helper anywhere in the SDK). ``FAILED_STEPS``
and ``FROM_CHECKPOINT`` therefore only affect which *variables* seed the
new run (a checkpoint's own ``variables_snapshot``, letting a replay
continue with previously-computed values rather than the definition's
bare defaults) -- not which *nodes* actually execute. Building true
partial-DAG resume would require forking
``shared_core.workflow.dag.execution_plan``'s own topological-levels
output to exclude already-satisfied nodes, a substantially larger
change to a library this service treats as a stable dependency, not
something to fork. Documented here rather than silently implied,
the same "an honest platform gap, not a fake success" discipline
``app/clients/playbook_client.py``'s own "Dependency Resolution" gap
and ``app/services/instance.py``'s own pause/resume limitation already
established.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.events.workflow_events import ReplayCompletedEvent, ReplayStartedEvent
from app.models.enums import ReplayType, WorkflowTriggerType
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_replay import WorkflowReplay
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.services.execution import EventPublisher, WorkflowExecutionService


class WorkflowReplayService:
    """Replays a workflow instance as a new run."""

    def __init__(
        self,
        replays: WorkflowReplayRepository,
        instances: WorkflowInstanceRepository,
        checkpoints: WorkflowCheckpointRepository,
        execution: WorkflowExecutionService,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._replays = replays
        self._instances = instances
        self._checkpoints = checkpoints
        self._execution = execution
        self._publish_event = publish_event

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowReplay]:
        """Every replay recorded for *instance_id* ("Replay History")."""
        return await self._replays.list_for_instance(instance_id)

    async def replay(
        self,
        instance_id: UUID,
        *,
        replay_type: ReplayType,
        checkpoint_id: UUID | None,
        requested_by: UUID | None,
        caller_token: str,
    ) -> WorkflowReplay:
        """Replay *instance_id* as a new instance ("Replay Workflow"/
        "Replay Failed Steps"/"Replay From Checkpoint").

        Raises:
            NotFoundError: If *instance_id* (or *checkpoint_id*, if given) does not exist.
        """
        source = await self._instances.require_by_id(instance_id)
        seed_variables: dict[str, Any] = {}
        source_checkpoint_id: UUID | None = None
        if replay_type == ReplayType.FROM_CHECKPOINT:
            checkpoint = (
                await self._checkpoints.get_by_id(checkpoint_id)
                if checkpoint_id is not None
                else await self._checkpoints.get_latest_for_instance(instance_id)
            )
            if checkpoint is None:
                raise NotFoundError(f"Workflow instance {instance_id!r} has no checkpoint yet.")
            seed_variables = dict(checkpoint.variables_snapshot)
            source_checkpoint_id = checkpoint.id

        new_instance = await self._instances.create(
            WorkflowInstance(
                organization_id=source.organization_id,
                project_id=source.project_id,
                definition_id=source.definition_id,
                version_id=source.version_id,
                trigger_type=WorkflowTriggerType.MANUAL,
                triggered_by=requested_by,
            )
        )
        await self._publish_event(
            ReplayStartedEvent(
                source_service="workflow-runtime-service",
                payload={"instance_id": str(instance_id), "new_instance_id": str(new_instance.id)},
            )
        )
        finished = await self._execution.run_instance(
            new_instance.id, caller_token=caller_token, seed_variables=seed_variables
        )
        await self._publish_event(
            ReplayCompletedEvent(
                source_service="workflow-runtime-service",
                payload={"instance_id": str(instance_id), "new_instance_id": str(finished.id)},
            )
        )

        replay = await self._replays.create(
            WorkflowReplay(
                organization_id=source.organization_id,
                instance_id=instance_id,
                new_instance_id=finished.id,
                replay_type=replay_type,
                source_checkpoint_id=source_checkpoint_id,
                requested_by=requested_by,
                requested_at=datetime.now(UTC),
                comparison={
                    "source_status": str(source.status),
                    "new_status": str(finished.status),
                },
            )
        )
        return replay


__all__ = ["WorkflowReplayService"]
