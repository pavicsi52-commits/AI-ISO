"""Background worker: workflow instance execution dispatch.

Per docs/042 "PERFORMANCE": Async Workers, Queue Integration,
Distributed Execution, Horizontal Scaling. ``POST /workflows/{id}
/execute`` creates the
:class:`~app.models.workflow_instance.WorkflowInstance` row and
enqueues onto :data:`EXECUTION_QUEUE_NAME` rather than blocking the
HTTP request for a workflow's own (potentially long-running) runtime --
this worker is what actually calls
:meth:`~app.services.execution.WorkflowExecutionService.run_instance`,
the same in-process queue-consumer pattern
``services/automation-service``'s own ``execution_worker`` established.

The queue message carries the triggering caller's own Bearer token,
needed for any ``TASK``/``CONNECTOR`` node to dispatch against
``services/automation-service`` mid-run -- for a schedule-fired (not
interactively-triggered) instance, no caller identity exists yet (no
service-account/machine-credential mechanism has been established by
any prior AI-IOS prompt), the same documented, honest platform gap
``services/automation-service``'s own ``execution_worker`` already
flagged.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.execution import WorkflowExecutionService

logger = get_logger("app.workers.execution_worker")

EXECUTION_QUEUE_NAME = "workflow_execution_queue"

ExecutionServiceFactory = Callable[[], AbstractAsyncContextManager[WorkflowExecutionService]]


def build_execution_worker(service_factory: ExecutionServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`EXECUTION_QUEUE_NAME`."""

    async def handle_execution_job(message: QueueMessage) -> None:
        instance_id = UUID(str(message["instance_id"]))
        caller_token = message.get("caller_token")
        if not caller_token:
            logger.warning(
                "Skipping workflow instance dispatch: no caller identity available "
                "to dispatch TASK/CONNECTOR nodes.",
                extra={"extra_fields": {"instance_id": str(instance_id)}},
            )
            return
        seed_variables = dict(message.get("variables") or {})
        try:
            async with service_factory() as execution:
                await execution.run_instance(
                    instance_id, caller_token=str(caller_token), seed_variables=seed_variables
                )
        except Exception:
            logger.exception(
                "Workflow instance dispatch failed.",
                extra={"extra_fields": {"instance_id": str(instance_id)}},
            )
            raise

    return job(EXECUTION_QUEUE_NAME)(handle_execution_job)


__all__ = ["EXECUTION_QUEUE_NAME", "ExecutionServiceFactory", "build_execution_worker"]
