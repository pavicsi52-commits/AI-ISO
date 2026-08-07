"""SyncService: queues and runs a connector's own synchronization jobs.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test. ``run()``
processes a caller-supplied ``records`` batch through the job's own
connector transformations (``TransformationService.apply_all``) -- these
tests prove the service's own bookkeeping (status transitions, checkpoint/
resume, success/failure counters, published events), not the transformation
engine's own behaviour in depth (covered by ``test_transformation_service.py``
and the pure engine's own tests).

To make ``apply_all`` genuinely raise for a given record (rather than
faking an exception), a real ``FIELD_MAPPING`` transformation is attached
to the connector and a non-mapping value (an ``int``) is passed as the
"record" at that index: ``app/transformations/engine.py``'s
``apply_field_mapping`` starts with ``dict(data)``, which raises a genuine
``TypeError`` for a non-iterable value -- a real failure the engine itself
produces, not a stubbed one.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import (
    ConflictResolution,
    SyncMode,
    SyncStatus,
    SyncTrigger,
    TransformationKind,
)
from app.services.sync import SyncService
from app.services.transformation import TransformationService

pytestmark = pytest.mark.asyncio


async def _attach_field_mapping(
    transformation_service: TransformationService, organization_id: uuid.UUID, connector_id
) -> None:
    """A real transformation rule whose engine call raises for a non-dict record."""
    await transformation_service.create(
        organization_id,
        connector_id=connector_id,
        name="identity-mapping",
        kind=TransformationKind.FIELD_MAPPING,
        config={"mapping": {"a": "a"}},
    )


class TestTrigger:
    async def test_creates_a_pending_job_with_default_fields(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        assert job.id is not None
        assert job.organization_id == organization_id
        assert job.connector_id == connector.id
        assert job.status == SyncStatus.PENDING
        assert job.mode == SyncMode.ONE_WAY
        assert job.trigger == SyncTrigger.MANUAL
        assert job.conflict_resolution == ConflictResolution.SOURCE_WINS
        assert job.triggered_by is None
        assert job.records_processed == 0
        assert job.records_succeeded == 0
        assert job.records_failed == 0
        assert job.checkpoint == {}
        assert job.started_at is None
        assert job.completed_at is None

    async def test_creates_with_custom_fields(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(
            organization_id,
            connector_id=connector.id,
            mode=SyncMode.TWO_WAY,
            trigger=SyncTrigger.SCHEDULED,
            conflict_resolution=ConflictResolution.TARGET_WINS,
            triggered_by="scheduler",
        )

        assert job.mode == SyncMode.TWO_WAY
        assert job.trigger == SyncTrigger.SCHEDULED
        assert job.conflict_resolution == ConflictResolution.TARGET_WINS
        assert job.triggered_by == "scheduler"


class TestGet:
    async def test_returns_the_matching_job(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await sync_service.trigger(organization_id, connector_id=connector.id)

        found = await sync_service.get(organization_id, created.id)

        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, sync_service: SyncService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await sync_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await sync_service.trigger(organization_id, connector_id=connector.id)

        with pytest.raises(NotFoundError):
            await sync_service.get(uuid.uuid4(), created.id)


class TestListForOrg:
    async def test_filters_by_status(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        pending = await sync_service.trigger(organization_id, connector_id=connector.id)
        running = await sync_service.trigger(organization_id, connector_id=connector.id)
        await sync_service.run(organization_id, running, records=[{"a": 1}])

        rows = await sync_service.list_for_org(organization_id, status=SyncStatus.PENDING)

        ids = [row.id for row in rows]
        assert pending.id in ids
        assert running.id not in ids

    async def test_filters_by_connector(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector_a = await make_connector(name="connector-a")
        connector_b = await make_connector(name="connector-b")
        job_a = await sync_service.trigger(organization_id, connector_id=connector_a.id)
        await sync_service.trigger(organization_id, connector_id=connector_b.id)

        rows = await sync_service.list_for_org(organization_id, connector_id=connector_a.id)

        assert [row.id for row in rows] == [job_a.id]

    async def test_is_tenant_scoped(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        await sync_service.trigger(organization_id, connector_id=connector.id)

        rows = await sync_service.list_for_org(uuid.uuid4())

        assert rows == []

    async def test_respects_limit(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        for _ in range(3):
            await sync_service.trigger(organization_id, connector_id=connector.id)

        rows = await sync_service.list_for_org(organization_id, limit=2)

        assert len(rows) == 2


class TestRunAllSucceed:
    async def test_marks_completed_with_full_success_counts(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        result = await sync_service.run(
            organization_id, job, records=[{"id": 1}, {"id": 2}, {"id": 3}]
        )

        assert result.status == SyncStatus.COMPLETED
        assert result.records_processed == 3
        assert result.records_succeeded == 3
        assert result.records_failed == 0
        assert result.error is None
        assert result.started_at is not None
        assert result.completed_at is not None

    async def test_publishes_started_then_completed_never_failed(
        self,
        sync_service: SyncService,
        organization_id: uuid.UUID,
        make_connector,
        publisher,
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        await sync_service.run(organization_id, job, records=[{"id": 1}])

        assert publisher.names == ["SynchronizationStarted", "SynchronizationCompleted"]

    async def test_runs_records_through_the_connectors_own_transformations(
        self,
        sync_service: SyncService,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="rename",
            kind=TransformationKind.FIELD_MAPPING,
            config={"mapping": {"old": "new"}},
        )
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        # A well-formed dict record survives the attached FIELD_MAPPING rule
        # (it only renames a key -- no exception), so this stays all-success.
        result = await sync_service.run(organization_id, job, records=[{"old": "value"}])

        assert result.status == SyncStatus.COMPLETED
        assert result.records_succeeded == 1


class TestRunAllFail:
    async def test_marks_failed_when_every_record_errors(
        self,
        sync_service: SyncService,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        await _attach_field_mapping(transformation_service, organization_id, connector.id)
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        # Non-dict "records" -- `apply_field_mapping`'s own `dict(data)` call
        # raises a genuine `TypeError` for each one.
        result = await sync_service.run(organization_id, job, records=[1, 2, 3])

        assert result.status == SyncStatus.FAILED
        assert result.records_processed == 3
        assert result.records_succeeded == 0
        assert result.records_failed == 3
        assert result.error is not None
        assert "not iterable" in result.error

    async def test_publishes_started_then_failed_never_completed(
        self,
        sync_service: SyncService,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
        publisher,
    ) -> None:
        connector = await make_connector()
        await _attach_field_mapping(transformation_service, organization_id, connector.id)
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        await sync_service.run(organization_id, job, records=[1])

        assert publisher.names == ["SynchronizationStarted", "SynchronizationFailed"]


class TestRunPartial:
    async def test_marks_partially_completed_with_mixed_counts(
        self,
        sync_service: SyncService,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector = await make_connector()
        await _attach_field_mapping(transformation_service, organization_id, connector.id)
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        # index 0 and 2 are real dicts (succeed); index 1 is an int (fails).
        result = await sync_service.run(organization_id, job, records=[{"a": 1}, 999, {"a": 3}])

        assert result.status == SyncStatus.PARTIALLY_COMPLETED
        assert result.records_processed == 3
        assert result.records_succeeded == 2
        assert result.records_failed == 1
        assert result.error is not None

    async def test_publishes_started_then_completed_not_failed(
        self,
        sync_service: SyncService,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
        publisher,
    ) -> None:
        connector = await make_connector()
        await _attach_field_mapping(transformation_service, organization_id, connector.id)
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        await sync_service.run(organization_id, job, records=[{"a": 1}, 999])

        assert publisher.names == ["SynchronizationStarted", "SynchronizationCompleted"]


class TestRunCheckpointResume:
    async def test_a_second_run_resumes_from_the_checkpoint_instead_of_reprocessing(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)
        first_batch = [{"id": 1}, {"id": 2}, {"id": 3}]

        first_result = await sync_service.run(organization_id, job, records=first_batch)

        assert first_result.checkpoint == {"last_index": 2}
        assert first_result.records_processed == 3
        assert first_result.records_succeeded == 3
        assert first_result.status == SyncStatus.COMPLETED

        # Same job object, same first three records, plus two new ones.
        second_batch = [*first_batch, {"id": 4}, {"id": 5}]
        second_result = await sync_service.run(organization_id, job, records=second_batch)

        # If the first three records had been reprocessed this would be 8,
        # not 5 -- the checkpoint must have skipped indices 0-2 entirely.
        assert second_result.records_processed == 5
        assert second_result.records_succeeded == 5
        assert second_result.records_failed == 0
        assert second_result.checkpoint == {"last_index": 4}
        assert second_result.status == SyncStatus.COMPLETED

    async def test_resume_publishes_a_fresh_started_and_completed_pair_each_call(
        self,
        sync_service: SyncService,
        organization_id: uuid.UUID,
        make_connector,
        publisher,
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        await sync_service.run(organization_id, job, records=[{"id": 1}, {"id": 2}])
        await sync_service.run(organization_id, job, records=[{"id": 1}, {"id": 2}, {"id": 3}])

        assert publisher.names == [
            "SynchronizationStarted",
            "SynchronizationCompleted",
            "SynchronizationStarted",
            "SynchronizationCompleted",
        ]

    async def test_a_resumed_run_with_no_new_records_processes_nothing_further(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)
        batch = [{"id": 1}, {"id": 2}]

        await sync_service.run(organization_id, job, records=batch)
        second_result = await sync_service.run(organization_id, job, records=batch)

        assert second_result.records_processed == 2
        assert second_result.records_succeeded == 2
        assert second_result.checkpoint == {"last_index": 1}

    async def test_started_at_is_not_overwritten_by_a_resumed_run(
        self, sync_service: SyncService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        job = await sync_service.trigger(organization_id, connector_id=connector.id)

        first_result = await sync_service.run(organization_id, job, records=[{"id": 1}])
        first_started_at = first_result.started_at

        second_result = await sync_service.run(organization_id, job, records=[{"id": 1}, {"id": 2}])

        assert second_result.started_at == first_started_at


class TestRunWithoutAPublisher:
    async def test_a_service_built_without_a_publisher_does_not_raise(
        self,
        sync_jobs_repo,
        transformation_service: TransformationService,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        service = SyncService(sync_jobs_repo, transformation_service, publish_event=None)
        connector = await make_connector()
        job = await service.trigger(organization_id, connector_id=connector.id)

        result = await service.run(organization_id, job, records=[{"id": 1}])

        assert result.status == SyncStatus.COMPLETED
