"""Background worker: bulk user import processing.

Per docs/031 "PERFORMANCE": "Background Import". Registered on this
service's own :class:`~shared_core.queue.consumer.Consumer` at startup
(see ``app/core/factory.py``'s ``_lifespan``) rather than run as a
separate deployable process -- a queue-backed background job either
way, just consumed in the same process that publishes it. Splitting
into a dedicated worker process later needs no redesign: this module's
handler has no dependency on the FastAPI app itself, only on the
service-factory context manager it's given.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.import_service import UserImportService

logger = get_logger("app.workers.import_worker")

IMPORT_QUEUE_NAME = "user_import_queue"

ImportServiceFactory = Callable[[], AbstractAsyncContextManager[UserImportService]]


def build_import_worker(service_factory: ImportServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`IMPORT_QUEUE_NAME`.

    *service_factory* is an async context manager factory: entering it
    opens a fresh database session scoped to this one job (commit on
    success, rollback on exception -- the same
    :func:`~shared_core.database.session.session_scope` guarantee every
    HTTP request already gets) and yields a
    :class:`~app.services.import_service.UserImportService` built on
    it. A bare ``session_factory()`` with no explicit commit was tried
    first and caught live: the job's own row (and the users it created)
    were flushed within the worker's session but never committed, so a
    client polling ``GET /users/import/{job_id}`` on its own,
    independently-committed session saw the job stuck at "queued"
    forever, exactly the cross-session-visibility bug this service's
    sibling (``services/authentication-service``) had already caught
    and fixed for its own ``get_db_session`` HTTP dependency.
    """

    async def handle_import_job(message: QueueMessage) -> None:
        job_id = UUID(str(message["job_id"]))
        try:
            async with service_factory() as service:
                await service.process_job(job_id)
        except Exception:
            logger.exception(
                "User import job failed.", extra={"extra_fields": {"job_id": str(job_id)}}
            )
            raise

    return job(IMPORT_QUEUE_NAME)(handle_import_job)


__all__ = ["IMPORT_QUEUE_NAME", "ImportServiceFactory", "build_import_worker"]
