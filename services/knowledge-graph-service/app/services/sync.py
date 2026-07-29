"""Synchronization as a service.

Wraps :class:`~app.synchronization.engine.SynchronizationEngine` with
the parts a run needs beyond the merge: the completion event, the
failure notification, and a version marker so "what did the graph look
like before last night's sync?" stays answerable.

**A version is recorded after a successful run, not before.** Recording
it first would leave a marker describing a graph state that the failed
run never produced.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.graph_events import SOURCE_SERVICE, GraphSynchronizedEvent
from app.models.enums import ConflictResolution, SyncMode, SyncSource, SyncStatus
from app.models.graph_sync_job import GraphSyncJob
from app.notifications.graph_notifications import GraphNotificationService
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.synchronization.engine import SynchronizationEngine, source_of, status_of
from app.types import EventPublisher
from app.versioning.snapshots import SnapshotService

logger = get_logger("app.services.sync")


class SyncService:
    """Runs synchronization and announces what it did."""

    def __init__(
        self,
        engine: SynchronizationEngine,
        jobs: GraphSyncJobRepository,
        snapshots: SnapshotService,
        notifications: GraphNotificationService,
        *,
        publish_event: EventPublisher,
        version_on_success: bool = True,
    ) -> None:
        self._engine = engine
        self._jobs = jobs
        self._snapshots = snapshots
        self._notifications = notifications
        self._publish_event = publish_event
        self._version_on_success = version_on_success

    async def sync_source(
        self,
        organization_id: UUID,
        source: SyncSource,
        *,
        mode: SyncMode = SyncMode.INCREMENTAL,
        conflict_resolution: ConflictResolution = ConflictResolution.SOURCE_WINS,
        actor_id: UUID | None = None,
    ) -> GraphSyncJob:
        """Synchronize one source and announce the outcome."""
        job = await self._engine.sync_source(
            organization_id,
            source,
            mode=mode,
            conflict_resolution=conflict_resolution,
            actor_id=actor_id,
        )
        await self._announce(organization_id, job, actor_id=actor_id)
        return job

    async def sync_all(
        self,
        organization_id: UUID,
        *,
        sources: list[SyncSource] | None = None,
        mode: SyncMode = SyncMode.INCREMENTAL,
        actor_id: UUID | None = None,
        version_label: str | None = None,
    ) -> dict[str, Any]:
        """Synchronize every source, then record one version marker.

        One marker for the whole run rather than one per source: a
        version describes the graph, and the graph only reaches its new
        shape once every source has finished.
        """
        jobs = await self._engine.sync_all(
            organization_id, sources=sources, mode=mode, actor_id=actor_id
        )
        for job in jobs:
            await self._announce(organization_id, job, actor_id=actor_id)

        succeeded = [job for job in jobs if status_of(job) is SyncStatus.SUCCEEDED]
        failed = [
            str(source_of(job))
            for job in jobs
            if status_of(job) in (SyncStatus.FAILED, SyncStatus.DISABLED)
        ]

        version = None
        if self._version_on_success and succeeded:
            version = await self._snapshots.create_version(
                organization_id,
                label=version_label or f"sync {len(succeeded)}/{len(jobs)} sources",
                description=(
                    f"{len(succeeded)} of {len(jobs)} sources synchronized"
                    + (f"; failed: {', '.join(failed)}" if failed else "")
                ),
                actor_id=actor_id,
            )

        return {
            "jobs": [
                {
                    "source": str(source_of(job)),
                    "status": str(status_of(job)),
                    "nodes": job.nodes_created,
                    "relationships": job.relationships_created,
                    "deleted": job.nodes_deleted,
                    "error": job.error,
                }
                for job in jobs
            ],
            "succeeded": len(succeeded),
            "failed_sources": failed,
            "version_sequence": version.sequence if version is not None else None,
        }

    async def history(
        self,
        organization_id: UUID,
        *,
        source: SyncSource | None = None,
        status: SyncStatus | None = None,
        limit: int = 100,
    ) -> list[GraphSyncJob]:
        """Sync runs, most recent first."""
        return await self._jobs.list_for_org(
            organization_id, source=source, status=status, limit=limit
        )

    async def reset_source(self, organization_id: UUID, source: SyncSource) -> GraphSyncJob | None:
        """Re-enable a source the engine disabled after repeated failures.

        Clears the cursor as well as the failure count, so the next run
        is effectively a fresh start: a source that broke badly enough to
        be disabled has usually also invalidated wherever its change feed
        had got to.
        """
        latest = await self._jobs.latest_for_source(organization_id, source)
        if latest is None:
            return None
        latest.status = SyncStatus.PENDING
        latest.consecutive_failures = 0
        latest.cursor = None
        latest.error = None
        logger.info(
            "Re-enabled a disabled sync source.",
            extra={"extra_fields": {"source": str(source)}},
        )
        return await self._jobs.update(latest)

    async def _announce(
        self, organization_id: UUID, job: GraphSyncJob, *, actor_id: UUID | None
    ) -> None:
        """Publish the completion event and notify on failure."""
        status = status_of(job)
        source = source_of(job)
        await self._publish_event(
            GraphSynchronizedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "source": str(source),
                    "status": str(status),
                    "nodes": job.nodes_created,
                    "relationships": job.relationships_created,
                },
            )
        )
        if status in (SyncStatus.FAILED, SyncStatus.DISABLED) and actor_id is not None:
            await self._notifications.send_sync_failed(
                str(actor_id),
                source=str(source),
                reason=job.error or "the run did not complete",
            )


__all__ = ["SyncService"]
