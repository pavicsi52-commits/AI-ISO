"""Data synchronization (docs/058 "DATA SYNCHRONIZATION")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.events.hub_events import (
    SOURCE_SERVICE,
    SynchronizationCompletedEvent,
    SynchronizationFailedEvent,
    SynchronizationStartedEvent,
)
from app.models.enums import ConflictResolution, SyncMode, SyncStatus, SyncTrigger
from app.models.sync import ConnectorSyncJob
from app.repositories.sync import ConnectorSyncJobRepository
from app.services.transformation import TransformationService
from app.types import EventPublisher


class SyncService:
    """Runs one connector's own synchronization jobs.

    A sync job processes the *records* its own caller supplies (docs/058
    describes what synchronization must support -- one/two-way,
    incremental/full, checkpointing/resume, conflict resolution -- not a
    live third-party data source this service has no concrete client
    for, the same "catalog/registry, not literal working integrations"
    scope boundary docs/058's own OBJECTIVE section states). Each record
    is run through the connector's own enabled transformations before
    being counted as processed.
    """

    def __init__(
        self,
        sync_jobs: ConnectorSyncJobRepository,
        transformations: TransformationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._sync_jobs = sync_jobs
        self._transformations = transformations
        self._publish = publish_event

    async def trigger(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID,
        mode: SyncMode = SyncMode.ONE_WAY,
        trigger: SyncTrigger = SyncTrigger.MANUAL,
        conflict_resolution: ConflictResolution = ConflictResolution.SOURCE_WINS,
        triggered_by: str | None = None,
    ) -> ConnectorSyncJob:
        """Queue a new sync job."""
        return await self._sync_jobs.create(
            ConnectorSyncJob(
                organization_id=organization_id,
                connector_id=connector_id,
                mode=mode,
                trigger=trigger,
                conflict_resolution=conflict_resolution,
                triggered_by=triggered_by,
                status=SyncStatus.PENDING,
            )
        )

    async def get(self, organization_id: UUID, sync_job_id: UUID) -> ConnectorSyncJob:
        """One sync job.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._sync_jobs.require_in_org(organization_id, sync_job_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID | None = None,
        status: SyncStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorSyncJob]:
        """Sync jobs in this organization, newest first."""
        return await self._sync_jobs.list_for_org(
            organization_id, connector_id=connector_id, status=status, limit=limit, offset=offset
        )

    async def run(
        self, organization_id: UUID, job: ConnectorSyncJob, *, records: list[dict[str, Any]]
    ) -> ConnectorSyncJob:
        """Process *records* through the job's own connector transformations.

        Resumable: a record already accounted for by the job's own
        ``checkpoint["last_index"]`` (from a prior partial run) is
        skipped, so calling this again with the same (or a longer)
        *records* list picks up where the last run left off.
        """
        job.status = SyncStatus.RUNNING
        job.started_at = job.started_at or datetime.now(UTC)
        await self._sync_jobs.update(job)
        await self._publish_event(
            SynchronizationStartedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"sync_job_id": str(job.id), "connector_id": str(job.connector_id)},
            )
        )

        start_index = int(job.checkpoint.get("last_index", -1)) + 1
        succeeded = 0
        failed = 0
        last_error: str | None = None

        for index in range(start_index, len(records)):
            try:
                await self._transformations.apply_all(job.connector_id, records[index])
                succeeded += 1
            except Exception as exc:
                failed += 1
                last_error = str(exc)
            job.checkpoint = {"last_index": index}

        job.records_processed += succeeded + failed
        job.records_succeeded += succeeded
        job.records_failed += failed
        job.completed_at = datetime.now(UTC)
        job.error = last_error

        if failed and not succeeded:
            job.status = SyncStatus.FAILED
        elif failed:
            job.status = SyncStatus.PARTIALLY_COMPLETED
        else:
            job.status = SyncStatus.COMPLETED
        await self._sync_jobs.update(job)

        if job.status == SyncStatus.FAILED:
            await self._publish_event(
                SynchronizationFailedEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={"sync_job_id": str(job.id), "error": last_error},
                )
            )
        else:
            await self._publish_event(
                SynchronizationCompletedEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={
                        "sync_job_id": str(job.id),
                        "records_succeeded": job.records_succeeded,
                        "records_failed": job.records_failed,
                    },
                )
            )
        return job

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["SyncService"]
