"""Background worker: periodic asset-management analytics recompute
and warranty/contract expiration sweep.

Per docs/038 "PERFORMANCE": "Background Analytics", "Queue
Integration". Recomputing an organization's statistics rollup on every
``GET /assets/analytics`` request (this service's on-demand fallback,
matching ``services/inventory-service``'s own ``InventoryStatisticsService
.get_for_org`` precedent) is fine for a cold cache, but this queue-
consumed job lets that recompute -- plus the warranty/contract
"Expiration Alerts"/"Contract Expiration" sweeps -- run periodically in
the background instead, keeping the cache warm without depending on
request traffic. Triggered by enqueueing ``{"organization_id": ...}``
onto :data:`SWEEP_QUEUE_NAME` (from an external scheduler, an admin
endpoint, or an operator's own cron); docs/038 names no dedicated
"SCHEDULE MANAGEMENT" section the way docs/037 did for
``services/discovery-service``, so this service integrates with the
queue framework (Prompt 020's own infrastructure) without also pulling
in the scheduler framework.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.queue.consumer import MessageHandler
from shared_core.queue.decorators import job
from shared_core.types.queue import QueueMessage

from app.services.contract import ContractService
from app.services.statistics import AssetStatisticsService
from app.services.warranty import WarrantyService

logger = get_logger("app.workers.sweep_worker")

SWEEP_QUEUE_NAME = "asset_management_sweep_queue"

SweepServices = tuple[AssetStatisticsService, WarrantyService, ContractService]
SweepServiceFactory = Callable[[], AbstractAsyncContextManager[SweepServices]]


def build_sweep_worker(service_factory: SweepServiceFactory) -> MessageHandler:
    """Build the ``@job``-decorated handler for :data:`SWEEP_QUEUE_NAME`."""

    async def handle_sweep_job(message: QueueMessage) -> None:
        organization_id = UUID(str(message["organization_id"]))
        try:
            async with service_factory() as (statistics, warranty, contract):
                await statistics.recompute(organization_id)
                await warranty.sweep_expiring()
                await contract.sweep_expiring()
        except Exception:
            logger.exception(
                "Asset management sweep failed.",
                extra={"extra_fields": {"organization_id": str(organization_id)}},
            )
            raise

    return job(SWEEP_QUEUE_NAME)(handle_sweep_job)


__all__ = ["SWEEP_QUEUE_NAME", "SweepServiceFactory", "SweepServices", "build_sweep_worker"]
