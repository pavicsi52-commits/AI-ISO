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


class TestAutomationClient:
    async def test_execute_and_wait_completes_on_first_poll(
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
            json={"data": {"id": execution_id, "status": "completed"}},
        )
        result = await automation_client.execute_and_wait(job_id, variables={"x": 1})
        assert result["status"] == "completed"

    async def test_execute_and_wait_polls_until_terminal(
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
            json={"data": {"id": execution_id, "status": "running"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={"data": {"id": execution_id, "status": "completed"}},
        )
        result = await automation_client.execute_and_wait(job_id, variables={})
        assert result["status"] == "completed"

    async def test_execute_and_wait_raises_on_failed_execution(
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
            json={"data": {"id": execution_id, "status": "failed", "error_message": "boom"}},
        )
        with pytest.raises(DependencyError, match="failed"):
            await automation_client.execute_and_wait(job_id, variables={})

    async def test_execute_and_wait_dispatch_failure_raises(
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

    async def test_execute_and_wait_dispatch_unreachable_raises(
        self, httpx_mock: HTTPXMock, automation_client: AutomationClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await automation_client.execute_and_wait(uuid.uuid4(), variables={})

    async def test_execute_and_wait_poll_unreachable_raises(
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

    async def test_execute_and_wait_poll_server_error_raises(
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
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await automation_client.execute_and_wait(job_id, variables={})

    async def test_execute_and_wait_exhausts_poll_attempts_raises(
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
