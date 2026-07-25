"""Worker.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "ACCEPTANCE
CRITERIA"/"JOB EXECUTION": pulls due jobs off the queue, executes them,
and reports its own liveness. Ties together
:class:`~shared_core.scheduler.queue.JobQueue` (where due job ids
arrive), :class:`~shared_core.scheduler.registry.JobRegistry` (resolves
a job id back to its full ``Job``, including ``fn``),
:class:`~shared_core.scheduler.executor.JobExecutor` (runs it),
:class:`~shared_core.scheduler.engine.SchedulerEngine` (recomputes its
next run once finished), and
:class:`~shared_core.scheduler.heartbeat.HeartbeatSender` ("Heartbeat").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.engine import SchedulerEngine
from shared_core.scheduler.exceptions import JobNotFoundError
from shared_core.scheduler.executor import ExecutionResult, JobExecutor
from shared_core.scheduler.heartbeat import HeartbeatSender
from shared_core.scheduler.middleware import ExecuteHandler
from shared_core.scheduler.queue import JobQueue
from shared_core.scheduler.registry import JobRegistry

logger = logging.getLogger(__name__)


class Worker:
    """Consumes due job ids from a :class:`JobQueue` and executes them.

    Runs every job through *handler* -- defaulting to plain
    ``executor.execute`` -- so a caller may instead pass a
    :func:`shared_core.scheduler.middleware.apply_middleware`-composed
    handler (built from *executor*'s own ``execute``) to run the full
    "MIDDLEWARE" chain around every execution, without this class
    needing to know anything about middleware itself.
    """

    def __init__(
        self,
        node_id: str,
        registry: JobRegistry,
        engine: SchedulerEngine,
        queue: JobQueue,
        executor: JobExecutor,
        *,
        heartbeat: HeartbeatSender | None = None,
        handler: ExecuteHandler | None = None,
    ) -> None:
        self._node_id = node_id
        self._registry = registry
        self._engine = engine
        self._queue = queue
        self._executor = executor
        self._heartbeat = heartbeat
        self._handler: ExecuteHandler = handler if handler is not None else executor.execute

    async def start(self) -> None:
        """Begin consuming and running due jobs, and start heartbeating if configured."""
        if self._heartbeat is not None:
            await self._heartbeat.start()
        await self._queue.consume(self._handle_job_id)

    async def stop(self) -> None:
        """Stop heartbeating ("Graceful Shutdown")."""
        if self._heartbeat is not None:
            await self._heartbeat.stop()

    async def _handle_job_id(self, job_id: str) -> None:
        try:
            job = self._registry.get(job_id)
        except JobNotFoundError:
            logger.warning("Worker %s received unknown job id %s; dropping.", self._node_id, job_id)
            return

        self._registry.transition(job_id, JobStatus.RUNNING, last_run=datetime.now(UTC))
        result = await self._handler(job)
        self._record_result(job_id, result)

    def _record_result(self, job_id: str, result: ExecutionResult) -> None:
        if result.succeeded:
            self._engine.advance(job_id, completed_at=result.finished_at)
            return
        if result.attempts == 0:
            # The job never actually ran here: either another worker already
            # holds its exclusive lock, or a middleware (e.g. security/tenant
            # validation) denied it before reaching the executor. Neither is
            # this worker's failure to report.
            return
        self._registry.transition(job_id, JobStatus.FAILED)
        logger.warning(
            "Job %s failed after %d attempt(s): %s", job_id, result.attempts, result.error
        )


__all__ = ["Worker"]
