"""Background worker: bulk project export processing.

See ``app/workers/import_worker.py``'s docstring for the shared
in-process queue-consumer pattern this mirrors.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.export_service import ProjectExportService

logger = get_logger("app.workers.export_worker")

EXPORT_QUEUE_NAME = "project_export_queue"

ExportServiceFactory = Callable[[], AbstractAsyncContextManager[ProjectExportService]]


def build_export_worker(service_factory: ExportServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`EXPORT_QUEUE_NAME`."""

    async def handle_export_job(message: QueueMessage) -> None:
        job_id = UUID(str(message["job_id"]))
        try:
            async with service_factory() as service:
                await service.process_job(job_id)
        except Exception:
            logger.exception(
                "Project export job failed.", extra={"extra_fields": {"job_id": str(job_id)}}
            )
            raise

    return job(EXPORT_QUEUE_NAME)(handle_export_job)


__all__ = ["EXPORT_QUEUE_NAME", "ExportServiceFactory", "build_export_worker"]
