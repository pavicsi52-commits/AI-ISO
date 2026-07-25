"""Scheduler manager.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "DIRECTORY
STRUCTURE"/"ACCEPTANCE CRITERIA": the top-level entry point tying every
other module in this framework together -- job registration, the
leader-only due-job dispatch loop, worker execution, and graceful
startup/shutdown. Nothing in this module implements scheduling behavior
itself; it only wires together modules that already do (``registry``,
``engine``, ``queue``, ``executor``, ``worker``, ``leader``,
``heartbeat``, ``failover``, ``history``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.audit import (
    audit_cancellation,
    audit_pause,
    audit_registration,
    audit_resume,
)
from shared_core.scheduler.constants import DEFAULT_POLL_INTERVAL_SECONDS
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.executor import JobExecutor
from shared_core.scheduler.failover import FailoverCoordinator
from shared_core.scheduler.heartbeat import HeartbeatSender
from shared_core.scheduler.history import HistoryStore
from shared_core.scheduler.job import Job
from shared_core.scheduler.leader import LeaderElection
from shared_core.scheduler.middleware import ExecuteHandler
from shared_core.scheduler.queue import JobQueue
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.worker import Worker

logger = logging.getLogger(__name__)


def new_node_id() -> str:
    """Generate a unique id for this scheduler process ("Node Registration")."""
    return str(uuid.uuid4())


class SchedulerManager:
    """The top-level entry point: registration, dispatch, and execution, wired together."""

    def __init__(
        self,
        registry: JobRegistry,
        engine: SchedulerEngine,
        queue: JobQueue,
        executor: JobExecutor,
        *,
        node_id: str | None = None,
        heartbeat: HeartbeatSender | None = None,
        leader: LeaderElection | None = None,
        failover: FailoverCoordinator | None = None,
        history: HistoryStore | None = None,
        handler: ExecuteHandler | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.node_id = node_id or new_node_id()
        self.registry = registry
        self.engine = engine
        self.queue = queue
        self.history = history if history is not None else HistoryStore()
        self.heartbeat = heartbeat
        self.leader = leader
        self.failover = failover
        self._poll_interval_seconds = poll_interval_seconds
        self.worker = Worker(self.node_id, registry, engine, queue, executor, handler=handler)
        self._dispatch_task: asyncio.Task[None] | None = None

    def register_job(self, job: Job) -> Job:
        """Register a new job and compute its first due time ("Job Registration")."""
        self.registry.register(job)
        audit_registration(job.job_id, job.job_name)
        return self.engine.schedule_initial_run(job.job_id)

    def pause_job(self, job_id: str) -> Job:
        """Pause a job ("Pause")."""
        job = self.registry.pause(job_id)
        audit_pause(job_id)
        return job

    def resume_job(self, job_id: str) -> Job:
        """Resume a paused job ("Resume")."""
        job = self.registry.resume(job_id)
        audit_resume(job_id)
        return job

    def cancel_job(self, job_id: str) -> Job:
        """Cancel a job ("Cancellation")."""
        job = self.registry.cancel(job_id)
        audit_cancellation(job_id)
        return job

    async def start(self) -> None:
        """Start heartbeat, leader election, failover, the dispatch loop, and the worker."""
        if self.heartbeat is not None:
            await self.heartbeat.start()
        if self.leader is not None:
            await self.leader.start()
        if self.failover is not None:
            await self.failover.start()
        await self.queue.declare()
        await self.worker.start()
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        """Stop every background component, in reverse start order ("Graceful Shutdown")."""
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatch_task
            self._dispatch_task = None
        await self.worker.stop()
        if self.failover is not None:
            await self.failover.stop()
        if self.leader is not None:
            await self.leader.stop()
        if self.heartbeat is not None:
            await self.heartbeat.stop()

    async def dispatch_due_jobs(self) -> list[str]:
        """Enqueue every currently-due job exactly once, returning their ids.

        Only does anything when this node is the elected leader (if
        leader election is configured) -- "Split-Brain Prevention": a
        non-leader node never independently decides what's due.
        """
        if self.leader is not None and not self.leader.is_leader:
            return []
        dispatched: list[str] = []
        for job in self.engine.due_jobs():
            self.registry.transition(job.job_id, JobStatus.QUEUED)
            await self.queue.enqueue(job.job_id)
            dispatched.append(job.job_id)
        return dispatched

    async def _dispatch_loop(self) -> None:
        while True:
            try:
                await self.dispatch_due_jobs()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler dispatch loop failed for node %s.", self.node_id)
            await asyncio.sleep(self._poll_interval_seconds)


__all__ = ["SchedulerManager", "new_node_id"]
