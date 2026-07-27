"""Tests for :mod:`app.collectors.service_state` -- collectors reading
another service's own already-recorded state, via real clients bound
to ``pytest-httpx``-mocked HTTP responses.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.clients.automation_client import AutomationClient
from app.clients.configuration_client import ConfigurationClient
from app.clients.discovery_client import DiscoveryClient
from app.clients.inventory_client import InventoryClient
from app.clients.workflow_client import WorkflowRuntimeClient
from app.collectors.context import CollectorContext
from app.collectors.service_state import (
    collect_configuration_compliance,
    collect_configuration_drift,
    collect_discovery_job,
    collect_inventory_asset,
    collect_inventory_topology,
    collect_workflow_instance,
)
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


def _check(
    check_type: ValidationCheckType, *, parameters: dict[str, object] | None = None
) -> ValidationCheck:
    return ValidationCheck(
        organization_id=uuid.uuid4(),
        check_type=check_type,
        name="test-check",
        collector_key="test",
        parameters=parameters or {},
    )


def _target(organization_id: uuid.UUID, external_id: uuid.UUID) -> ValidationTarget:
    return ValidationTarget(
        organization_id=organization_id,
        target_type=ValidationTargetType.CONFIGURATION_PROFILE,
        external_id=str(external_id),
        name="test-target",
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
                client, base_url=AUTOMATION_SERVICE_BASE_URL, caller_token="tok"
            ),
            workflow=WorkflowRuntimeClient(
                client, base_url=WORKFLOW_SERVICE_BASE_URL, caller_token="tok"
            ),
            discovery=DiscoveryClient(
                client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="tok"
            ),
        )


class TestCollectInventoryAsset:
    async def test_returns_asset_status(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        asset_id = uuid.uuid4()
        target = _target(uuid.uuid4(), asset_id)
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/assets/{asset_id}",
            json={"data": {"id": str(asset_id), "status": "active"}},
        )
        data = await collect_inventory_asset(
            _check(ValidationCheckType.CONFIGURATION), target, context
        )
        assert data["status"] == "active"


class TestCollectInventoryTopology:
    async def test_returns_node_count(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        asset_id = uuid.uuid4()
        target = _target(uuid.uuid4(), asset_id)
        httpx_mock.add_response(
            url=f"{INVENTORY_SERVICE_BASE_URL}/inventory/topology"
            f"?asset_id={asset_id}&query_kind=neighbors&depth=1",
            json={"data": {"nodes": [{"id": str(uuid.uuid4())}, {"id": str(uuid.uuid4())}]}},
        )
        data = await collect_inventory_topology(
            _check(ValidationCheckType.NETWORK), target, context
        )
        assert data["node_count"] == 2


class TestCollectConfigurationDrift:
    async def test_counts_unresolved_drift(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        org_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        target = _target(org_id, profile_id)
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/drift"
            f"?organization_id={org_id}&profile_id={profile_id}",
            json={
                "data": [
                    {"id": str(uuid.uuid4()), "resolved_at": None},
                    {"id": str(uuid.uuid4()), "resolved_at": "2026-01-01T00:00:00Z"},
                ]
            },
        )
        data = await collect_configuration_drift(
            _check(ValidationCheckType.CONFIGURATION), target, context
        )
        assert data["unresolved_drift_count"] == 1


class TestCollectConfigurationCompliance:
    async def test_counts_non_compliant(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        profile_id = uuid.uuid4()
        target = _target(uuid.uuid4(), profile_id)
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/compliance"
            f"?profile_id={profile_id}",
            json={"data": [{"status": "compliant"}, {"status": "non_compliant"}]},
        )
        data = await collect_configuration_compliance(
            _check(ValidationCheckType.COMPLIANCE_POLICIES), target, context
        )
        assert data["non_compliant_count"] == 1


class TestCollectWorkflowInstance:
    async def test_counts_failed_steps(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        instance_id = uuid.uuid4()
        target = _target(uuid.uuid4(), instance_id)
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}",
            json={"data": {"status": "failed"}},
        )
        httpx_mock.add_response(
            url=f"{WORKFLOW_SERVICE_BASE_URL}/workflow-instances/{instance_id}/steps",
            json={"data": [{"status": "completed"}, {"status": "failed"}]},
        )
        data = await collect_workflow_instance(_check(ValidationCheckType.CUSTOM), target, context)
        assert data["instance_status"] == "failed"
        assert data["failed_step_count"] == 1


class TestCollectDiscoveryJob:
    async def test_returns_summary(self, httpx_mock: HTTPXMock, context: CollectorContext) -> None:
        job_id = uuid.uuid4()
        target = _target(uuid.uuid4(), job_id)
        httpx_mock.add_response(
            url=f"{DISCOVERY_SERVICE_BASE_URL}/discovery/jobs/{job_id}",
            json={
                "data": {
                    "status": "completed",
                    "discovered_asset_count": 10,
                    "discovered_relationship_count": 3,
                }
            },
        )
        data = await collect_discovery_job(_check(ValidationCheckType.CUSTOM), target, context)
        assert data["discovered_asset_count"] == 10
