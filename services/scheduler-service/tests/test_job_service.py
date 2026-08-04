"""JobService: creation, editing, and status lifecycle.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from tests.conftest import utcnow

from app.models.enums import JobPriority, JobType, ScheduledJobStatus
from app.services.job import JobService

pytestmark = pytest.mark.asyncio


class TestCreate:
    async def test_creates_a_job_directly_active(
        self, job_service: JobService, organization_id
    ) -> None:
        created = await job_service.create(
            organization_id, name="Nightly backup", job_type=JobType.BACKUP_JOB
        )
        assert created.status == ScheduledJobStatus.ACTIVE
        assert created.name == "Nightly backup"
        assert created.job_type == JobType.BACKUP_JOB

    async def test_uses_default_field_values(
        self, job_service: JobService, organization_id
    ) -> None:
        created = await job_service.create(
            organization_id, name="Custom job", job_type=JobType.CUSTOM_JOB
        )
        assert created.priority == JobPriority.NORMAL
        assert created.timezone == "UTC"
        assert created.payload == {}
        assert created.job_metadata == {}
        assert created.tags == []
        assert created.timeout_seconds is None
        assert created.run_count == 0
        assert created.failure_count == 0

    async def test_records_two_history_rows_registered_then_active(
        self, job_service: JobService, organization_id, history_repo
    ) -> None:
        created = await job_service.create(
            organization_id, name="Report generation", job_type=JobType.REPORT_GENERATION
        )
        rows = await history_repo.list_for_job(organization_id, created.id)
        assert len(rows) == 2
        assert rows[0].from_status is None
        assert rows[0].to_status == str(ScheduledJobStatus.REGISTERED)
        assert rows[1].from_status == str(ScheduledJobStatus.REGISTERED)
        assert rows[1].to_status == str(ScheduledJobStatus.ACTIVE)

    async def test_sets_created_by_from_actor_id(
        self, job_service: JobService, organization_id
    ) -> None:
        actor_id = uuid4()
        created = await job_service.create(
            organization_id, name="AI task", job_type=JobType.AI_TASK, actor_id=str(actor_id)
        )
        assert created.created_by == actor_id

    async def test_leaves_created_by_none_without_an_actor_id(
        self, job_service: JobService, organization_id
    ) -> None:
        created = await job_service.create(
            organization_id, name="Cleanup job", job_type=JobType.CLEANUP_JOB
        )
        assert created.created_by is None


class TestGet:
    async def test_raises_not_found_for_a_missing_job(
        self, job_service: JobService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await job_service.get(organization_id, uuid4())

    async def test_is_scoped_to_its_organization(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        with pytest.raises(NotFoundError):
            await job_service.get(uuid4(), created.id)


class TestListJobs:
    async def test_filters_by_status(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        active_job = await make_job("Active job")
        paused_job = await make_job("Paused job")
        await job_service.pause(organization_id, paused_job.id)

        active_only = await job_service.list_jobs(organization_id, status=ScheduledJobStatus.ACTIVE)
        ids = {one.id for one in active_only}
        assert active_job.id in ids
        assert paused_job.id not in ids
        assert all(one.status == ScheduledJobStatus.ACTIVE for one in active_only)

    async def test_filters_by_job_type(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        backup = await make_job("Backup", job_type=JobType.BACKUP_JOB)
        await make_job("Discovery", job_type=JobType.DISCOVERY_JOB)
        found = await job_service.list_jobs(organization_id, job_type=JobType.BACKUP_JOB)
        ids = {one.id for one in found}
        assert backup.id in ids
        assert all(one.job_type == JobType.BACKUP_JOB for one in found)

    async def test_filters_by_priority(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        high = await make_job("High priority", priority=JobPriority.HIGH)
        await make_job("Low priority", priority=JobPriority.LOW)
        found = await job_service.list_jobs(organization_id, priority=JobPriority.HIGH)
        ids = {one.id for one in found}
        assert high.id in ids
        assert all(one.priority == JobPriority.HIGH for one in found)

    async def test_filters_by_owner_id(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        owned = await make_job("Owned by alice", owner_id="alice")
        await make_job("Owned by bob", owner_id="bob")
        found = await job_service.list_jobs(organization_id, owner_id="alice")
        ids = {one.id for one in found}
        assert owned.id in ids
        assert all(one.owner_id == "alice" for one in found)


class TestUpdate:
    async def test_updates_editable_fields(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        updated = await job_service.update(
            organization_id,
            created.id,
            name="Renamed job",
            description="New description",
            priority=JobPriority.HIGH,
            owner_id="alice",
            timezone="America/New_York",
            payload={"key": "value"},
            job_metadata={"meta": True},
            tags=["a", "b"],
            timeout_seconds=120.0,
        )
        assert updated.name == "Renamed job"
        assert updated.description == "New description"
        assert updated.priority == JobPriority.HIGH
        assert updated.owner_id == "alice"
        assert updated.timezone == "America/New_York"
        assert updated.payload == {"key": "value"}
        assert updated.job_metadata == {"meta": True}
        assert updated.tags == ["a", "b"]
        assert updated.timeout_seconds == 120.0

    async def test_silently_ignores_a_status_field_and_leaves_it_unchanged(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        updated = await job_service.update(organization_id, created.id, status="deleted")
        assert updated.status == ScheduledJobStatus.ACTIVE

    async def test_silently_ignores_a_job_type_field(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job(job_type=JobType.CUSTOM_JOB)
        updated = await job_service.update(organization_id, created.id, job_type=JobType.BACKUP_JOB)
        assert updated.job_type == JobType.CUSTOM_JOB

    async def test_sets_updated_by_from_actor_id(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        actor_id = uuid4()
        updated = await job_service.update(
            organization_id, created.id, actor_id=str(actor_id), name="Renamed"
        )
        assert updated.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_job(
        self, job_service: JobService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await job_service.update(organization_id, uuid4(), name="Nope")


class TestPause:
    async def test_pauses_an_active_job_and_sets_paused_at(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        updated = await job_service.pause(organization_id, created.id)
        assert updated.status == ScheduledJobStatus.PAUSED
        assert updated.paused_at is not None

    async def test_raises_validation_error_if_the_job_is_not_active(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.pause(organization_id, created.id)
        with pytest.raises(ValidationError):
            await job_service.pause(organization_id, created.id)

    async def test_records_a_history_row_for_the_transition(
        self, job_service: JobService, organization_id, make_job, history_repo
    ) -> None:
        created = await make_job()
        await job_service.pause(organization_id, created.id)
        rows = await history_repo.list_for_job(organization_id, created.id)
        assert rows[-1].from_status == str(ScheduledJobStatus.ACTIVE)
        assert rows[-1].to_status == str(ScheduledJobStatus.PAUSED)


class TestResume:
    async def test_resumes_a_paused_job_and_clears_paused_at(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.pause(organization_id, created.id)
        updated = await job_service.resume(organization_id, created.id)
        assert updated.status == ScheduledJobStatus.ACTIVE
        assert updated.paused_at is None

    async def test_raises_validation_error_if_the_job_is_not_paused(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        with pytest.raises(ValidationError):
            await job_service.resume(organization_id, created.id)


class TestCancel:
    async def test_cancels_an_active_job_to_disabled_and_sets_disabled_at(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        updated = await job_service.cancel(organization_id, created.id, reason="No longer needed")
        assert updated.status == ScheduledJobStatus.DISABLED
        assert updated.disabled_at is not None

    async def test_cancels_a_paused_job_to_disabled(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.pause(organization_id, created.id)
        updated = await job_service.cancel(organization_id, created.id)
        assert updated.status == ScheduledJobStatus.DISABLED

    async def test_records_the_reason_as_the_history_rows_note(
        self, job_service: JobService, organization_id, make_job, history_repo
    ) -> None:
        created = await make_job()
        await job_service.cancel(organization_id, created.id, reason="Deprecated")
        rows = await history_repo.list_for_job(organization_id, created.id)
        assert rows[-1].note == "Deprecated"

    async def test_raises_validation_error_if_already_disabled(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.cancel(organization_id, created.id)
        with pytest.raises(ValidationError):
            await job_service.cancel(organization_id, created.id)


class TestDelete:
    async def test_deletes_an_active_job(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        updated = await job_service.delete(organization_id, created.id)
        assert updated.status == ScheduledJobStatus.DELETED

    async def test_deletes_a_disabled_job(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.cancel(organization_id, created.id)
        updated = await job_service.delete(organization_id, created.id)
        assert updated.status == ScheduledJobStatus.DELETED

    async def test_raises_validation_error_if_already_deleted(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.delete(organization_id, created.id)
        with pytest.raises(ValidationError):
            await job_service.delete(organization_id, created.id)


class TestRecordRun:
    async def test_increments_run_count_and_sets_last_run_at(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        ran_at = utcnow()
        await job_service.record_run(organization_id, created.id, ran_at=ran_at)
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.run_count == 1
        assert refetched.last_run_at == ran_at

    async def test_accumulates_across_multiple_runs(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.record_run(organization_id, created.id, ran_at=utcnow())
        await job_service.record_run(organization_id, created.id, ran_at=utcnow())
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.run_count == 2

    async def test_does_not_change_status(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.record_run(organization_id, created.id, ran_at=utcnow())
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.status == ScheduledJobStatus.ACTIVE

    async def test_raises_not_found_for_a_missing_job(
        self, job_service: JobService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await job_service.record_run(organization_id, uuid4(), ran_at=utcnow())


class TestRecordFailure:
    async def test_increments_the_failure_counter(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.record_failure(organization_id, created.id)
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.failure_count == 1

    async def test_accumulates_across_multiple_failures(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.record_failure(organization_id, created.id)
        await job_service.record_failure(organization_id, created.id)
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.failure_count == 2

    async def test_does_not_change_status(
        self, job_service: JobService, organization_id, make_job
    ) -> None:
        created = await make_job()
        await job_service.record_failure(organization_id, created.id)
        refetched = await job_service.get(organization_id, created.id)
        assert refetched.status == ScheduledJobStatus.ACTIVE

    async def test_raises_not_found_for_a_missing_job(
        self, job_service: JobService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await job_service.record_failure(organization_id, uuid4())
