"""Background worker: discovery job execution.

Per docs/037 "PERFORMANCE": "Async Discovery Workers". Registered on
this service's own :class:`~shared_core.queue.consumer.Consumer` at
startup (see ``app/core/factory.py``'s ``_lifespan``), the same
in-process queue-consumer pattern
``services/inventory-service``'s own ``import_worker`` established.

The queue message carries an optional ``caller_token`` -- present for
every interactively-triggered job (the ``POST /discovery/*`` request's
own Bearer token flows straight through), absent for a schedule-fired
job (see ``app/core/factory.py``'s schedule callback and
``app/services/discovery_execution.py``'s own module docstring for the
documented, honest limitation this produces).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.discovery_execution import DiscoveryExecutionService

logger = get_logger("app.workers.discovery_worker")

DISCOVERY_QUEUE_NAME = "discovery_execution_queue"

ExecutionServiceFactory = Callable[[], AbstractAsyncContextManager[DiscoveryExecutionService]]


def build_discovery_worker(service_factory: ExecutionServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`DISCOVERY_QUEUE_NAME`.

    *service_factory* is an async context manager factory: entering it
    opens a fresh database session scoped to this one job (commit on
    success, rollback on exception) and yields a
    :class:`~app.services.discovery_execution.DiscoveryExecutionService`
    built on it -- see ``services/inventory-service``'s identical
    ``build_import_worker`` docstring for the real cross-session-
    visibility bug this ``session_scope``-wrapped shape was already
    caught and fixed for.
    """

    async def handle_discovery_job(message: QueueMessage) -> None:
        job_id = UUID(str(message["job_id"]))
        caller_token = message.get("caller_token")
        try:
            async with service_factory() as service:
                await service.run_job(
                    job_id, caller_token=str(caller_token) if caller_token else None
                )
        except Exception:
            logger.exception(
                "Discovery job failed.", extra={"extra_fields": {"job_id": str(job_id)}}
            )
            raise

    return job(DISCOVERY_QUEUE_NAME)(handle_discovery_job)


__all__ = ["DISCOVERY_QUEUE_NAME", "ExecutionServiceFactory", "build_discovery_worker"]
