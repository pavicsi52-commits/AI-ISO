"""Background worker: automation execution dispatch.

Per docs/040 "PERFORMANCE": Async Execution, Distributed Workers, Queue
Framework Integration. ``POST /automation/jobs/{id}/execute`` creates
the :class:`~app.models.automation_execution.AutomationExecution` row
and enqueues onto :data:`EXECUTION_QUEUE_NAME` rather than blocking the
HTTP request for a job's own (potentially hour-long, per
``default_execution_timeout_seconds``) runtime -- this worker is what
actually calls :meth:`~app.services.execution.AutomationExecutionService
.run_execution`, the same in-process queue-consumer pattern
``services/configuration-management-service``'s own
``git_sync_worker``/``statistics_worker`` established.

The queue message carries the triggering caller's own Bearer token,
needed to resolve target credentials from
``services/secrets-management-service`` mid-dispatch -- for a
schedule-fired (not interactively-triggered) execution, no caller
identity exists yet (no service-account/machine-credential mechanism
has been established by any prior AI-IOS prompt), the same documented,
honest platform gap ``services/configuration-management-service``'s
own ``git_sync_worker`` already flagged.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.execution import AutomationExecutionService

logger = get_logger("app.workers.execution_worker")

EXECUTION_QUEUE_NAME = "automation_execution_queue"

ExecutionServiceFactory = Callable[[], AbstractAsyncContextManager[AutomationExecutionService]]


def build_execution_worker(service_factory: ExecutionServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`EXECUTION_QUEUE_NAME`."""

    async def handle_execution_job(message: QueueMessage) -> None:
        execution_id = UUID(str(message["execution_id"]))
        caller_token = message.get("caller_token")
        if not caller_token:
            logger.warning(
                "Skipping automation execution: no caller identity available "
                "to resolve target credentials.",
                extra={"extra_fields": {"execution_id": str(execution_id)}},
            )
            return
        try:
            async with service_factory() as executions:
                await executions.run_execution(execution_id, caller_token=str(caller_token))
        except Exception:
            logger.exception(
                "Automation execution dispatch failed.",
                extra={"extra_fields": {"execution_id": str(execution_id)}},
            )
            raise

    return job(EXECUTION_QUEUE_NAME)(handle_execution_job)


__all__ = ["EXECUTION_QUEUE_NAME", "ExecutionServiceFactory", "build_execution_worker"]
