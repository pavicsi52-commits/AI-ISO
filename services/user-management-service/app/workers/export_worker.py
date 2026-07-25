"""Background worker: bulk user export processing.

Per docs/031 "PERFORMANCE": "Background Export". See
:mod:`app.workers.import_worker`'s docstring for why this runs as a
registered queue subscriber in the main process rather than a
separately deployed worker, and for the real commit bug its
``service_factory`` async-context-manager shape was fixed to prevent.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.export_service import UserExportService

logger = get_logger("app.workers.export_worker")

EXPORT_QUEUE_NAME = "user_export_queue"

ExportServiceFactory = Callable[[], AbstractAsyncContextManager[UserExportService]]


def build_export_worker(service_factory: ExportServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`EXPORT_QUEUE_NAME`.

    *service_factory* is an async context manager factory -- see
    :func:`app.workers.import_worker.build_import_worker`'s docstring
    for why (commit-on-success session scoping per job).
    """

    async def handle_export_job(message: QueueMessage) -> None:
        job_id = UUID(str(message["job_id"]))
        try:
            async with service_factory() as service:
                await service.process_job(job_id)
        except Exception:
            logger.exception(
                "User export job failed.", extra={"extra_fields": {"job_id": str(job_id)}}
            )
            raise

    return job(EXPORT_QUEUE_NAME)(handle_export_job)


__all__ = ["EXPORT_QUEUE_NAME", "ExportServiceFactory", "build_export_worker"]
