"""Background worker: periodic configuration-management analytics recompute.

Per docs/039 "PERFORMANCE": "Background Drift Detection", "Queue
Integration"; "DRIFT DETECTION" "Schedule Periodic Drift Analysis".
Recomputing an organization's statistics rollup on every
``GET /configurations/analytics`` request (this service's on-demand
fallback, matching ``services/asset-management-service``'s own
``AssetStatisticsService.get_for_org`` precedent) is fine for a cold
cache, but this queue-consumed job lets that recompute -- including the
``drift_statistics`` rollup built from every already-recorded
:class:`~app.models.configuration_drift.ConfigurationDrift` row --
run periodically in the background instead, keeping the cache warm
without depending on request traffic. Actual drift *detection* (probing
live infrastructure for its actual state) is explicitly out of scope
(docs/039 "DO NOT IMPLEMENT": "Discovery Engine", "Monitoring Engine");
this worker only re-aggregates drift instances some other component
already reported via :meth:`~app.services.drift.ConfigurationDriftService
.report`. Triggered by enqueueing ``{"organization_id": ...}`` onto
:data:`STATISTICS_QUEUE_NAME` (from an external scheduler, an admin
endpoint, or an operator's own cron).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.statistics import ConfigurationStatisticsService

logger = get_logger("app.workers.statistics_worker")

STATISTICS_QUEUE_NAME = "configuration_management_statistics_queue"

StatisticsServiceFactory = Callable[[], AbstractAsyncContextManager[ConfigurationStatisticsService]]


def build_statistics_worker(service_factory: StatisticsServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`STATISTICS_QUEUE_NAME`."""

    async def handle_statistics_job(message: QueueMessage) -> None:
        organization_id = UUID(str(message["organization_id"]))
        try:
            async with service_factory() as statistics:
                await statistics.recompute(organization_id)
        except Exception:
            logger.exception(
                "Configuration management statistics recompute failed.",
                extra={"extra_fields": {"organization_id": str(organization_id)}},
            )
            raise

    return job(STATISTICS_QUEUE_NAME)(handle_statistics_job)


__all__ = ["STATISTICS_QUEUE_NAME", "StatisticsServiceFactory", "build_statistics_worker"]
