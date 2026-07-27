"""Workflow instance lifecycle: creation, lookup, and cooperative
pause/resume/cancel control.

Per docs/042's own literal REST list, ``pause``/``resume``/``cancel``/
``rollback``/``replay`` all live under ``/workflows/{id}/...`` (the
workflow *definition*'s own id), not ``/workflow-instances/{id}/...`` --
the same phrasing docs/040 used for
``/automation/jobs/{id}/cancel``/``/pause``/``/resume`` (acting on that
job's own *current* execution). Matching that already-resolved
precedent: every action here targets *definition_id*'s own most
recent, still-active instance, found via
:meth:`get_active_for_definition`.

**Pause/resume/cancel are cooperative and metadata-only, an honest
limitation, not a gap silently glossed over.**
``shared_core.workflow.WorkflowEngine.run()`` has no pause/resume/
cancel entry point of its own (confirmed: it is a single
uninterruptible ``await`` from the caller's own perspective), and
``shared_core.workflow.WorkflowRuntime.cancel()`` only works for a task
started in *this same process* -- since actual execution happens in a
queue-consumed background worker (``app/workers/execution_worker.py``),
not inline with the pause/resume/cancel request, there is no live
``asyncio.Task`` for these actions to reach into. Setting
``status=PAUSED``/``CANCELLED`` here only prevents a not-yet-dispatched
instance from starting, or records caller intent for audit -- an
already-*running* instance keeps running to its own natural
completion, the same "cooperative, not preemptive" limitation
``services/automation-service``'s own pause/cancel handling already
accepted. Genuinely continuing a stopped run happens through
``POST /workflows/{id}/replay`` with ``replay_type=from_checkpoint``,
not through ``resume``.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import WorkflowInstanceStatus, WorkflowTriggerType
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.services.state import WorkflowStateTransitionService

_ACTIVE_STATUSES = frozenset(
    {
        WorkflowInstanceStatus.CREATED,
        WorkflowInstanceStatus.QUEUED,
        WorkflowInstanceStatus.WAITING,
        WorkflowInstanceStatus.RUNNING,
        WorkflowInstanceStatus.PAUSED,
        WorkflowInstanceStatus.CHECKPOINTED,
        WorkflowInstanceStatus.RETRYING,
    }
)


class WorkflowInstanceService:
    """Creates, reads, and cooperatively controls workflow instances."""

    def __init__(
        self, instances: WorkflowInstanceRepository, states: WorkflowStateTransitionService
    ) -> None:
        self._instances = instances
        self._states = states

    async def get_by_id(self, instance_id: UUID) -> WorkflowInstance:
        """Return the instance identified by *instance_id*.

        Raises:
            NotFoundError: If no such instance exists.
        """
        return await self._instances.require_by_id(instance_id)

    async def list_for_org(
        self, organization_id: UUID, *, status: WorkflowInstanceStatus | None = None
    ) -> list[WorkflowInstance]:
        """Every instance belonging to *organization_id*, newest first."""
        return await self._instances.list_for_org(organization_id, status=status)

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowInstance]:
        """Every instance run of *definition_id*, newest first."""
        return await self._instances.list_for_definition(definition_id)

    async def get_active_for_definition(self, definition_id: UUID) -> WorkflowInstance:
        """Return *definition_id*'s own most recent, still-active instance.

        Raises:
            NotFoundError: If *definition_id* has never been executed,
                or every prior instance has already reached a terminal state.
        """
        for instance in await self._instances.list_for_definition(definition_id):
            if instance.status in _ACTIVE_STATUSES:
                return instance
        raise NotFoundError(f"Workflow {definition_id!r} has no active instance.")

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        definition_id: UUID,
        version_id: UUID,
        trigger_type: WorkflowTriggerType,
        triggered_by: UUID | None,
    ) -> WorkflowInstance:
        """Create a new, not-yet-dispatched instance ("Execute")."""
        instance = await self._instances.create(
            WorkflowInstance(
                organization_id=organization_id,
                project_id=project_id,
                definition_id=definition_id,
                version_id=version_id,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
            )
        )
        await self._states.record(
            organization_id=organization_id,
            instance_id=instance.id,
            from_status=None,
            to_status=WorkflowInstanceStatus.QUEUED,
        )
        instance.status = WorkflowInstanceStatus.QUEUED
        return await self._instances.update(instance)

    async def pause(self, instance_id: UUID) -> WorkflowInstance:
        """Record caller intent to pause *instance_id* ("Pause").

        Raises:
            NotFoundError: If no such instance exists.
            ConflictError: If *instance_id* has already reached a terminal state.
        """
        return await self._transition_active(instance_id, WorkflowInstanceStatus.PAUSED)

    async def resume(self, instance_id: UUID) -> WorkflowInstance:
        """Mark a paused instance as runnable again ("Resume").

        Raises:
            NotFoundError: If no such instance exists.
            ConflictError: If *instance_id* has already reached a terminal state.
        """
        return await self._transition_active(instance_id, WorkflowInstanceStatus.RUNNING)

    async def cancel(self, instance_id: UUID) -> WorkflowInstance:
        """Record caller intent to cancel *instance_id* ("Cancel").

        Raises:
            NotFoundError: If no such instance exists.
            ConflictError: If *instance_id* has already reached a terminal state.
        """
        return await self._transition_active(instance_id, WorkflowInstanceStatus.CANCELLED)

    async def _transition_active(
        self, instance_id: UUID, to_status: WorkflowInstanceStatus
    ) -> WorkflowInstance:
        instance = await self.get_by_id(instance_id)
        if instance.status not in _ACTIVE_STATUSES:
            raise ConflictError(
                f"Workflow instance {instance_id!r} is already {str(instance.status)!r} "
                f"and cannot be transitioned further."
            )
        await self._states.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=instance.status,
            to_status=to_status,
        )
        instance.status = to_status
        return await self._instances.update(instance)


__all__ = ["WorkflowInstanceService"]
