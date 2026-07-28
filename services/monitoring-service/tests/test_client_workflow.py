"""Tests for :class:`app.clients.workflow_client.WorkflowRuntimeClient`
against real documented Workflow Runtime Service response shapes, via
``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.workflow_client import WorkflowRuntimeClient
from tests.conftest import WORKFLOW_SERVICE_BASE_URL


@pytest.fixture
async def workflow_client() -> AsyncIterator[WorkflowRuntimeClient]:
    async with httpx.AsyncClient() as client:
        yield WorkflowRuntimeClient(client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="tok")


class TestGetInstance:
    async def test_returns_record(
        self, httpx_mock: HTTPXMock, workflow_client: WorkflowRuntimeClient
    ) -> None:
        instance_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}",
            json={"data": {"id": str(instance_id), "status": "completed"}},
        )
        instance = await workflow_client.get_instance(instance_id)
        assert instance["status"] == "completed"

    async def test_missing_raises(
        self, httpx_mock: HTTPXMock, workflow_client: WorkflowRuntimeClient
    ) -> None:
        instance_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}", status_code=404
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await workflow_client.get_instance(instance_id)

    async def test_unreachable_raises(
        self, httpx_mock: HTTPXMock, workflow_client: WorkflowRuntimeClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await workflow_client.get_instance(uuid.uuid4())


class TestListSteps:
    async def test_returns_steps(
        self, httpx_mock: HTTPXMock, workflow_client: WorkflowRuntimeClient
    ) -> None:
        instance_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}/steps",
            json={"data": [{"id": str(uuid.uuid4()), "status": "failed"}]},
        )
        steps = await workflow_client.list_steps(instance_id)
        assert steps[0]["status"] == "failed"

    async def test_failure_raises(
        self, httpx_mock: HTTPXMock, workflow_client: WorkflowRuntimeClient
    ) -> None:
        instance_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}/steps",
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await workflow_client.list_steps(instance_id)
