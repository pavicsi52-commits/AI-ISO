"""Background worker: bulk asset import processing.

Per docs/036 "PERFORMANCE": "Background Processing". Registered on this
service's own :class:`~shared_core.queue.consumer.Consumer` at startup
(see ``app/core/factory.py``'s ``_lifespan``), the same in-process
queue-consumer pattern ``services/project-service``'s own
``import_worker`` established.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.import_service import AssetImportService

logger = get_logger("app.workers.import_worker")

IMPORT_QUEUE_NAME = "inventory_import_queue"

ImportServiceFactory = Callable[[], AbstractAsyncContextManager[AssetImportService]]


def build_import_worker(service_factory: ImportServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`IMPORT_QUEUE_NAME`.

    *service_factory* is an async context manager factory: entering it
    opens a fresh database session scoped to this one job (commit on
    success, rollback on exception) and yields an
    :class:`~app.services.import_service.AssetImportService` built on
    it -- see ``services/project-service``'s identical
    ``build_import_worker`` docstring for the real cross-session-
    visibility bug this ``session_scope``-wrapped shape was already
    caught and fixed for.
    """

    async def handle_import_job(message: QueueMessage) -> None:
        job_id = UUID(str(message["job_id"]))
        try:
            async with service_factory() as service:
                await service.process_job(job_id)
        except Exception:
            logger.exception(
                "Asset import job failed.", extra={"extra_fields": {"job_id": str(job_id)}}
            )
            raise

    return job(IMPORT_QUEUE_NAME)(handle_import_job)


__all__ = ["IMPORT_QUEUE_NAME", "ImportServiceFactory", "build_import_worker"]
