"""Tests for :mod:`app.scheduling.scheduler_integration`."""

from __future__ import annotations

import uuid

from shared_core.scheduler.job import JobType

from app.models.automation_schedule import AutomationSchedule
from app.scheduling.scheduler_integration import build_scheduler_job


def _schedule(**overrides: object) -> AutomationSchedule:
    defaults: dict[str, object] = {
        "organization_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "cron_expression": "0 * * * *",
        "enabled": True,
    }
    defaults.update(overrides)
    schedule = AutomationSchedule(**defaults)
    schedule.id = uuid.uuid4()
    return schedule


class TestBuildSchedulerJob:
    def test_builds_job_with_automation_type(self) -> None:
        schedule = _schedule()
        job = build_scheduler_job(schedule, trigger=lambda *_: None)  # type: ignore[arg-type]
        assert job.job_type == JobType.AUTOMATION
        assert job.job_name == f"automation-schedule-{schedule.id}"
        assert job.schedule.cron_expression == "0 * * * *"
        assert job.organization_id == str(schedule.organization_id)
        assert job.payload["schedule_id"] == str(schedule.id)
        assert job.payload["job_id"] == str(schedule.job_id)

    async def test_running_job_calls_trigger_with_job_and_org_id(self) -> None:
        schedule = _schedule()
        calls: list[tuple[uuid.UUID, uuid.UUID]] = []

        async def _trigger(job_id: uuid.UUID, organization_id: uuid.UUID) -> None:
            calls.append((job_id, organization_id))

        job = build_scheduler_job(schedule, trigger=_trigger)
        await job.fn(job)

        assert calls == [(schedule.job_id, schedule.organization_id)]
