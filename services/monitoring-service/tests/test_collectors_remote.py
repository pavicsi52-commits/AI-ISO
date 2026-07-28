"""Tests for :mod:`app.collectors.remote` -- the automation-job
delegation collector for OS-level metrics this service has no direct
remote-execution capability of its own to perform.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.collectors.remote import collect_via_automation_job
from app.models.enums import MonitoringTargetType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget
from tests.conftest import AUTOMATION_SERVICE_BASE_URL, build_collector_context


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield build_collector_context(client)


def _collector(*, parameters: dict[str, object] | None = None) -> MonitoringCollector:
    return MonitoringCollector(
        organization_id=uuid.uuid4(),
        name="test-collector",
        collector_key="automation_job",
        parameters=parameters or {},
    )


def _target(external_id: str) -> MonitoringTarget:
    return MonitoringTarget(
        organization_id=uuid.uuid4(),
        target_type=MonitoringTargetType.PHYSICAL_SERVER,
        external_id=external_id,
        name="test-target",
    )


class TestCollectViaAutomationJob:
    async def test_returns_job_result(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        target_id = uuid.uuid4()
        collector = _collector(parameters={"job_id": str(job_id)})
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={
                "data": {
                    "id": execution_id,
                    "status": "completed",
                    "result": {"cpu_usage_percent": 42.5},
                }
            },
        )
        data = await collect_via_automation_job(collector, _target(str(target_id)), context)
        assert data["cpu_usage_percent"] == 42.5

    async def test_missing_job_id_raises(self, context: CollectorContext) -> None:
        collector = _collector()
        with pytest.raises(ValidationError, match="job_id"):
            await collect_via_automation_job(collector, _target(str(uuid.uuid4())), context)

    async def test_non_dict_result_falls_back_to_status(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        collector = _collector(parameters={"job_id": str(job_id)})
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={"data": {"id": execution_id, "status": "completed", "result": None}},
        )
        data = await collect_via_automation_job(collector, _target(str(uuid.uuid4())), context)
        assert data == {"execution_status": "completed"}
