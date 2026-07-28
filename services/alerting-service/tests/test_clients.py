"""Tests for every outbound HTTP client, via ``pytest-httpx`` against
each partner service's own real documented response shape -- never a
live account.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.monitoring_client import MonitoringClient
from app.clients.validation_client import ValidationClient
from app.clients.workflow_client import WorkflowRuntimeClient
from tests.conftest import (
    AUTOMATION_SERVICE_BASE_URL,
    CONFIGURATION_SERVICE_BASE_URL,
    DISCOVERY_SERVICE_BASE_URL,
    INVENTORY_SERVICE_BASE_URL,
    MONITORING_SERVICE_BASE_URL,
    VALIDATION_SERVICE_BASE_URL,
    WORKFLOW_SERVICE_BASE_URL,
)


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


class TestMonitoringClient:
    async def test_list_health_for_target(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        target = uuid.uuid4()
        httpx_mock.add_response(json={"data": [{"status": "unhealthy"}]})
        client = MonitoringClient(
            http_client, base_url=MONITORING_SERVICE_BASE_URL, caller_token="t"
        )
        assert await client.list_health_for_target(target) == [{"status": "unhealthy"}]

    async def test_list_dependency_children(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": [{"child_target_id": "x"}]})
        client = MonitoringClient(
            http_client, base_url=MONITORING_SERVICE_BASE_URL, caller_token="t"
        )
        assert len(await client.list_dependency_children(uuid.uuid4())) == 1

    async def test_unreachable_raises_dependency_error(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = MonitoringClient(
            http_client, base_url=MONITORING_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.list_health_for_target(uuid.uuid4())

    async def test_error_status_raises_dependency_error(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=500)
        client = MonitoringClient(
            http_client, base_url=MONITORING_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.list_dependency_children(uuid.uuid4())


class TestValidationClient:
    async def test_get_results_for_target(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": [{"status": "failed"}]})
        client = ValidationClient(
            http_client, base_url=VALIDATION_SERVICE_BASE_URL, caller_token="t"
        )
        assert len(await client.get_results_for_target(uuid.uuid4())) == 1

    async def test_error_status_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=503)
        client = ValidationClient(
            http_client, base_url=VALIDATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.get_results_for_target(uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = ValidationClient(
            http_client, base_url=VALIDATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.get_results_for_target(uuid.uuid4())


class TestWorkflowClient:
    async def test_get_instance(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": {"status": "completed"}})
        client = WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="t"
        )
        assert (await client.get_instance(uuid.uuid4()))["status"] == "completed"

    async def test_execute_workflow_posts_to_the_real_endpoint(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        """The real endpoint is POST /workflows/{id}/execute, returning 201."""
        workflow_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflows/{workflow_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": str(uuid.uuid4()), "status": "pending"}},
        )
        client = WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="t"
        )
        result = await client.execute_workflow(workflow_id, variables={"alert_id": "x"})
        assert result["status"] == "pending"

    async def test_execute_rejects_non_201(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=404)
        client = WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.execute_workflow(uuid.uuid4(), variables={})

    async def test_get_instance_error_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=404)
        client = WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.get_instance(uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = WorkflowRuntimeClient(
            http_client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.execute_workflow(uuid.uuid4(), variables={})


class TestAutomationClient:
    async def test_list_executions(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": [{"job_id": "a", "status": "failed"}]})
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        assert len(await client.list_executions(uuid.uuid4())) == 1

    async def test_list_executions_with_status_filter(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": []})
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        assert await client.list_executions(uuid.uuid4(), status="failed") == []

    async def test_latest_execution_filters_client_side(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        """The real endpoint has no job_id filter -- documented gap."""
        job_id = uuid.uuid4()
        httpx_mock.add_response(
            json={"data": [{"job_id": "other"}, {"job_id": str(job_id), "status": "failed"}]}
        )
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        found = await client.get_latest_execution_for_job(uuid.uuid4(), job_id)
        assert found is not None
        assert found["status"] == "failed"

    async def test_latest_execution_returns_none_when_absent(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(json={"data": [{"job_id": "other"}]})
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        assert await client.get_latest_execution_for_job(uuid.uuid4(), uuid.uuid4()) is None

    async def test_error_status_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=500)
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.list_executions(uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = AutomationClient(
            http_client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.list_executions(uuid.uuid4())


class TestConfigurationClient:
    async def test_get_drift(self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"data": [{"resolved_at": None}]})
        client = ConfigurationClient(
            http_client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token="t"
        )
        assert len(await client.get_drift(uuid.uuid4(), uuid.uuid4())) == 1

    async def test_error_status_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=500)
        client = ConfigurationClient(
            http_client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.get_drift(uuid.uuid4(), uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = ConfigurationClient(
            http_client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError):
            await client.get_drift(uuid.uuid4(), uuid.uuid4())


class TestDiscoveryClient:
    async def test_get_job(self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"data": {"status": "failed"}})
        client = DiscoveryClient(http_client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="t")
        assert (await client.get_job(uuid.uuid4()))["status"] == "failed"

    async def test_error_status_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=404)
        client = DiscoveryClient(http_client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="t")
        with pytest.raises(DependencyError):
            await client.get_job(uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = DiscoveryClient(http_client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="t")
        with pytest.raises(DependencyError):
            await client.get_job(uuid.uuid4())


class TestInventoryClient:
    async def test_get_asset(self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"data": {"status": "active"}})
        client = InventoryClient(http_client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token="t")
        assert (await client.get_asset(uuid.uuid4()))["status"] == "active"

    async def test_error_status_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(status_code=404)
        client = InventoryClient(http_client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token="t")
        with pytest.raises(DependencyError):
            await client.get_asset(uuid.uuid4())

    async def test_unreachable_raises(
        self, http_client: httpx.AsyncClient, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        client = InventoryClient(http_client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token="t")
        with pytest.raises(DependencyError):
            await client.get_asset(uuid.uuid4())
