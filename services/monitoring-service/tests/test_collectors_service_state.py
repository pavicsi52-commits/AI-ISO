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

from app.collectors.context import CollectorContext
from app.collectors.service_state import (
    collect_configuration_compliance,
    collect_configuration_drift,
    collect_discovery_job,
    collect_inventory_asset,
    collect_validation_posture,
    collect_workflow_instance,
)
from app.models.enums import MonitoringTargetType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget
from tests.conftest import (
    CONFIGURATION_SERVICE_BASE_URL,
    DISCOVERY_SERVICE_BASE_URL,
    INVENTORY_SERVICE_BASE_URL,
    VALIDATION_SERVICE_BASE_URL,
    WORKFLOW_SERVICE_BASE_URL,
    build_collector_context,
)


def _collector(collector_key: str) -> MonitoringCollector:
    return MonitoringCollector(
        organization_id=uuid.uuid4(), name="test-collector", collector_key=collector_key
    )


def _target(organization_id: uuid.UUID, external_id: uuid.UUID) -> MonitoringTarget:
    return MonitoringTarget(
        id=uuid.uuid4(),
        organization_id=organization_id,
        target_type=MonitoringTargetType.APPLICATION,
        external_id=str(external_id),
        name="test-target",
    )


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield build_collector_context(client)


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
        data = await collect_inventory_asset(_collector("inventory_asset"), target, context)
        assert data["status"] == "active"


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
        data = await collect_configuration_drift(_collector("configuration_drift"), target, context)
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
            _collector("configuration_compliance"), target, context
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
        data = await collect_workflow_instance(_collector("workflow_instance"), target, context)
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
        data = await collect_discovery_job(_collector("discovery_job"), target, context)
        assert data["discovered_asset_count"] == 10


class TestCollectValidationPosture:
    async def test_counts_failed_results(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        target = _target(uuid.uuid4(), uuid.uuid4())
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results?target_id={target.id}",
            json={"data": [{"status": "passed"}, {"status": "failed"}]},
        )
        data = await collect_validation_posture(_collector("validation_posture"), target, context)
        assert data["result_count"] == 2
        assert data["failed_count"] == 1
