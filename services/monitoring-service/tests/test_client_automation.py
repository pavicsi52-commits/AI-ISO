"""Tests for :class:`app.clients.automation_client.AutomationClient`
against real documented Automation Service response shapes, via
``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.automation_client import AutomationClient
from tests.conftest import AUTOMATION_SERVICE_BASE_URL


@pytest.fixture
async def automation_client() -> AsyncIterator[AutomationClient]:
    async with httpx.AsyncClient() as client:
        yield AutomationClient(
            client,
            base_url=AUTOMATION_SERVICE_BASE_URL,
            caller_token="tok",
            poll_interval_seconds=0.01,
            max_poll_attempts=5,
        )


class TestGetLatestExecutionForJob:
    async def test_finds_matching_execution(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        org_id = uuid.uuid4()
        job_id = uuid.uuid4()
        other_job_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions?organization_id={org_id}",
            json={
                "data": [
                    {"id": str(uuid.uuid4()), "job_id": str(other_job_id), "status": "completed"},
                    {"id": str(uuid.uuid4()), "job_id": str(job_id), "status": "failed"},
                ]
            },
        )
        execution = await automation_client.get_latest_execution_for_job(org_id, job_id)
        assert execution is not None
        assert execution["status"] == "failed"

    async def test_returns_none_when_job_never_ran(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        org_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions?organization_id={org_id}",
            json={"data": []},
        )
        execution = await automation_client.get_latest_execution_for_job(org_id, uuid.uuid4())
        assert execution is None

    async def test_failure_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        org_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions?organization_id={org_id}",
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await automation_client.get_latest_execution_for_job(org_id, uuid.uuid4())

    async def test_unreachable_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await automation_client.get_latest_execution_for_job(uuid.uuid4(), uuid.uuid4())


class TestExecuteAndWait:
    async def test_completes_on_first_poll(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={"data": {"id": execution_id, "status": "completed", "result": {"cpu": 42}}},
        )
        result = await automation_client.execute_and_wait(job_id, variables={"x": 1})
        assert result["status"] == "completed"

    async def test_dispatch_failure_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        job_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=404,
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await automation_client.execute_and_wait(job_id, variables={})

    async def test_exhausts_poll_attempts_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        for _ in range(5):
            httpx_mock.add_response(
                url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
                json={"data": {"id": execution_id, "status": "running"}},
            )
        with pytest.raises(DependencyError, match="did not reach a terminal status"):
            await automation_client.execute_and_wait(job_id, variables={})

    async def test_get_execution_unreachable_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await automation_client.execute_and_wait(job_id, variables={})
