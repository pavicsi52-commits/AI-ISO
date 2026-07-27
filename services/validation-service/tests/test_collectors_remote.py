"""Tests for :mod:`app.collectors.remote` -- the automation-job
delegation collector for OS-level check types this service has no
direct remote-execution capability of its own to perform.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.validation import ValidationError

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.workflow_client import WorkflowRuntimeClient
from app.collectors.context import CollectorContext
from app.collectors.remote import collect_via_automation_job
from app.models.enums import ValidationCheckType, ValidationTargetType
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget
from tests.conftest import (
    AUTOMATION_SERVICE_BASE_URL,
    CONFIGURATION_SERVICE_BASE_URL,
    DISCOVERY_SERVICE_BASE_URL,
    INVENTORY_SERVICE_BASE_URL,
    WORKFLOW_SERVICE_BASE_URL,
)


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield CollectorContext(
            inventory=InventoryClient(
                client, base_url=INVENTORY_SERVICE_BASE_URL, caller_token="tok"
            ),
            configuration=ConfigurationClient(
                client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token="tok"
            ),
            automation=AutomationClient(
                client,
                base_url=AUTOMATION_SERVICE_BASE_URL,
                caller_token="tok",
                poll_interval_seconds=0.01,
                max_poll_attempts=5,
            ),
            workflow=WorkflowRuntimeClient(
                client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="tok"
            ),
            discovery=DiscoveryClient(
                client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="tok"
            ),
        )


def _target(external_id: str) -> ValidationTarget:
    return ValidationTarget(
        organization_id=uuid.uuid4(),
        target_type=ValidationTargetType.PHYSICAL_SERVER,
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
        check = ValidationCheck(
            organization_id=uuid.uuid4(),
            check_type=ValidationCheckType.DISK_USAGE,
            name="disk-usage",
            collector_key="automation_job",
            parameters={"job_id": str(job_id)},
        )
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
                    "result": {"disk_usage_percent": 92.5},
                }
            },
        )
        data = await collect_via_automation_job(check, _target(str(target_id)), context)
        assert data["disk_usage_percent"] == 92.5

    async def test_missing_job_id_raises(self, context: CollectorContext) -> None:
        check = ValidationCheck(
            organization_id=uuid.uuid4(),
            check_type=ValidationCheckType.CPU,
            name="cpu",
            collector_key="automation_job",
            parameters={},
        )
        with pytest.raises(ValidationError, match="job_id"):
            await collect_via_automation_job(check, _target(str(uuid.uuid4())), context)

    async def test_non_dict_result_falls_back_to_status(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        check = ValidationCheck(
            organization_id=uuid.uuid4(),
            check_type=ValidationCheckType.MEMORY,
            name="memory",
            collector_key="automation_job",
            parameters={"job_id": str(job_id)},
        )
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
        data = await collect_via_automation_job(check, _target(str(uuid.uuid4())), context)
        assert data == {"execution_status": "completed"}
