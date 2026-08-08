"""The task dispatch sweep worker (docs/060 "TASK MANAGEMENT": Queue,
Scheduling; "PERFORMANCE": Execution Queues).

Finds every due, agent-assigned task and runs it through
:class:`~app.services.execution.ExecutionService`. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per task.** A failure on one task must not poison the
transaction the next one needs, and a task silently missing from a
sweep is worse than one that visibly failed.

A task with no ``agent_id`` yet is left ``PENDING`` -- this sweep
dispatches already-assigned work, it does not itself decide which
agent should take an unassigned task.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.registry import ModelRegistry
from app.graph.client import GraphClient
from app.memory.service import MemoryService
from app.models.enums import ExecutionStatus
from app.models.task import AgentTask
from app.repositories.agent import AgentRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.memory import AgentMemoryRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.tool import AgentToolRepository
from app.sandbox.policy import AgentSandboxPolicy
from app.services.execution import ExecutionService
from app.services.task import TaskService
from app.types import EventPublisher

logger = get_logger("app.workers.task_dispatch_sweep")


class TaskDispatchSweepWorker:
    """Dispatches every due, agent-assigned task to its own agent."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: ModelRegistry,
        *,
        http_client: httpx.AsyncClient,
        sandbox_policy: AgentSandboxPolicy,
        graph_client: GraphClient | None,
        automation_service_base_url: str,
        publish_event: EventPublisher,
        max_tasks_per_tick: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._http_client = http_client
        self._sandbox_policy = sandbox_policy
        self._graph_client = graph_client
        self._automation_service_base_url = automation_service_base_url
        self._publish_event = publish_event
        self._max_tasks_per_tick = max_tasks_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Dispatch every currently-due task; returns how many were attempted."""
        async with self._session_factory() as session:
            due = await AgentTaskRepository(session).list_due(
                datetime.now(UTC), limit=self._max_tasks_per_tick
            )
        attempted = 0
        for task in due:
            if task.agent_id is None:
                continue
            await self._dispatch_one(task)
            attempted += 1
        logger.info(
            "Task dispatch sweep complete.",
            extra={"extra_fields": {"due": len(due), "attempted": attempted}},
        )
        return attempted

    async def _dispatch_one(self, task: AgentTask) -> None:
        """Run one task through its own agent, under its own session."""
        try:
            async with self._session_factory() as session:
                tasks_repo = AgentTaskRepository(session)
                agents_repo = AgentRepository(session)
                task_service = TaskService(tasks_repo, publish_event=self._publish_event)

                live_task = await tasks_repo.require_in_org(task.organization_id, task.id)
                agent = await agents_repo.require_in_org(task.organization_id, task.agent_id)  # type: ignore[arg-type]

                live_task = await task_service.start(live_task)

                execution_service = ExecutionService(
                    agents_repo,
                    AgentProfileRepository(session),
                    AgentToolRepository(session),
                    AgentPermissionGrantRepository(session),
                    AgentExecutionRepository(session),
                    MemoryService(AgentMemoryRepository(session)),
                    self._registry,
                    http_client=self._http_client,
                    sandbox_policy=self._sandbox_policy,
                    graph_client=self._graph_client,
                    automation_service_base_url=self._automation_service_base_url,
                    session=session,
                    publish_event=self._publish_event,
                )
                request = str(live_task.payload.get("request", live_task.task_type))
                execution = await execution_service.execute_agent(
                    agent, request=request, task_id=live_task.id
                )

                if execution.status == ExecutionStatus.COMPLETED:
                    await task_service.complete(
                        live_task, result={"execution_id": str(execution.id)}
                    )
                else:
                    await task_service.fail(live_task, error=execution.error or "Execution failed.")
                await session.commit()
        except Exception as exc:
            logger.warning(
                "A task dispatch failed; the rest of the sweep continues.",
                extra={"extra_fields": {"task_id": str(task.id), "error": str(exc)}},
            )


__all__ = ["TaskDispatchSweepWorker"]
