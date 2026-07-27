"""Background worker: validation execution dispatch.

Per docs/043 "PERFORMANCE": Async Validation Workers, Queue
Integration, Distributed Execution, Horizontal Scaling.
``POST /validations/{id}/execute`` creates the
:class:`~app.models.validation_execution.ValidationExecution` row and
enqueues onto :data:`EXECUTION_QUEUE_NAME` rather than blocking the
HTTP request for a potentially long-running multi-target run -- this
worker is what actually calls
:meth:`~app.services.execution.ValidationExecutionService
.run_execution`, the same in-process queue-consumer pattern
``services/workflow-runtime-service``'s own ``execution_worker``
established.

The queue message carries the triggering caller's own Bearer token,
needed for every collector to dispatch against the other platform
services this execution validates against.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.execution import ValidationExecutionService

logger = get_logger("app.workers.execution_worker")

EXECUTION_QUEUE_NAME = "validation_execution_queue"

ExecutionServiceFactory = Callable[[], AbstractAsyncContextManager[ValidationExecutionService]]


def build_execution_worker(service_factory: ExecutionServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`EXECUTION_QUEUE_NAME`."""

    async def handle_execution_job(message: QueueMessage) -> None:
        execution_id = UUID(str(message["execution_id"]))
        caller_token = message.get("caller_token")
        if not caller_token:
            logger.warning(
                "Skipping validation execution dispatch: no caller identity available "
                "to dispatch collectors.",
                extra={"extra_fields": {"execution_id": str(execution_id)}},
            )
            return
        try:
            async with service_factory() as execution:
                await execution.run_execution(execution_id, caller_token=str(caller_token))
        except Exception:
            logger.exception(
                "Validation execution dispatch failed.",
                extra={"extra_fields": {"execution_id": str(execution_id)}},
            )
            raise

    return job(EXECUTION_QUEUE_NAME)(handle_execution_job)


__all__ = ["EXECUTION_QUEUE_NAME", "ExecutionServiceFactory", "build_execution_worker"]
