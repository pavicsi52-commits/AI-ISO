"""Task management (docs/060 "TASK MANAGEMENT"; backs ``GET/POST
/agents/tasks``)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.events.agent_events import TaskCompletedEvent, TaskCreatedEvent
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import AgentTask
from app.repositories.task import AgentTaskRepository
from app.types import EventPublisher

_TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT}
)


class TaskService:
    """Creates and transitions one agent task's own status."""

    def __init__(self, tasks: AgentTaskRepository, *, publish_event: EventPublisher) -> None:
        self._tasks = tasks
        self._publish_event = publish_event

    async def create_task(
        self,
        *,
        organization_id: UUID,
        task_type: str,
        payload: dict[str, Any],
        agent_id: UUID | None = None,
        parent_task_id: UUID | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 300.0,
        requested_by: str | None = None,
    ) -> AgentTask:
        """Queue a new task ("Creation", "Queue", "Scheduling")."""
        task = await self._tasks.create(
            AgentTask(
                organization_id=organization_id,
                agent_id=agent_id,
                parent_task_id=parent_task_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                priority=priority,
                payload=payload,
                checkpoint={},
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                scheduled_at=scheduled_at or datetime.now(UTC),
                requested_by=requested_by,
            )
        )
        await self._publish_event(
            TaskCreatedEvent(
                source_service="ai-agent-platform-service",
                organization_id=organization_id,
                payload={"task_id": str(task.id), "task_type": task_type},
            )
        )
        return task

    async def assign(self, task: AgentTask, *, agent_id: UUID) -> AgentTask:
        """Assign *task* to *agent_id* ("Assignment")."""
        task.agent_id = agent_id
        task.status = TaskStatus.ASSIGNED
        return await self._tasks.update(task)

    async def start(self, task: AgentTask) -> AgentTask:
        """Mark *task* as running."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(UTC)
        return await self._tasks.update(task)

    async def complete(self, task: AgentTask, *, result: dict[str, Any]) -> AgentTask:
        """Mark *task* completed and record its own result."""
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now(UTC)
        task = await self._tasks.update(task)
        await self._publish_event(
            TaskCompletedEvent(
                source_service="ai-agent-platform-service",
                organization_id=task.organization_id,
                payload={"task_id": str(task.id), "status": str(task.status)},
            )
        )
        return task

    async def fail(self, task: AgentTask, *, error: str) -> AgentTask:
        """Mark *task* failed, retrying it instead if it has attempts
        left ("Retry")."""
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.RETRYING
            task.error = error
            return await self._tasks.update(task)

        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.now(UTC)
        task = await self._tasks.update(task)
        await self._publish_event(
            TaskCompletedEvent(
                source_service="ai-agent-platform-service",
                organization_id=task.organization_id,
                payload={"task_id": str(task.id), "status": str(task.status)},
            )
        )
        return task

    async def cancel(self, task: AgentTask) -> AgentTask:
        """Cancel *task* ("Cancellation") -- a no-op if it already
        reached a terminal status."""
        if task.status in _TERMINAL_STATUSES:
            return task
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(UTC)
        return await self._tasks.update(task)


__all__ = ["TaskService"]
