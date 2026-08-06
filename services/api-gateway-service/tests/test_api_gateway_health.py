"""``GET /gateway/health`` -- aggregated backend health across every
registered service (docs/056 "REST APIs").

Probing itself happens on the worker sweep (see ``test_workers.py``);
this endpoint only ever reports whatever a
:class:`~app.services.health.HealthMonitorService` most recently
persisted, so tests here call ``probe()`` directly against real
endpoints rather than driving a whole sweep.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.health import HealthMonitorService

pytestmark = pytest.mark.asyncio

REACHABLE_URL = "http://127.0.0.1:15672/"
UNREACHABLE_URL = "http://127.0.0.1:1/"


class TestGatewayHealth:
    async def test_an_organization_with_no_probed_instances_is_unknown(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            "/gateway/health", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["overall_status"] == "unknown"
        assert data["instances"] == []

    async def test_overall_status_is_the_worst_of_every_instance(
        self,
        client: AsyncClient,
        health_monitor_service: HealthMonitorService,
        make_service,
        organization_id: uuid.UUID,
    ) -> None:
        healthy_service = await make_service(name="healthy-service")
        unhealthy_service = await make_service(name="unhealthy-service")

        await health_monitor_service.probe(
            organization_id, healthy_service.id, REACHABLE_URL, service_name=healthy_service.name
        )
        await health_monitor_service.probe(
            organization_id,
            unhealthy_service.id,
            UNREACHABLE_URL,
            service_name=unhealthy_service.name,
        )

        response = await client.get(
            "/gateway/health", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        # UNHEALTHY outranks HEALTHY -- one bad instance is enough to
        # mark the whole organization's own gateway health as bad.
        assert data["overall_status"] == "unhealthy"
        assert len(data["instances"]) == 2
        statuses = {row["instance_url"]: row["status"] for row in data["instances"]}
        assert statuses[REACHABLE_URL] == "healthy"
        assert statuses[UNREACHABLE_URL] == "unhealthy"

    async def test_a_single_healthy_instance_reports_healthy_overall(
        self,
        client: AsyncClient,
        health_monitor_service: HealthMonitorService,
        make_service,
        organization_id: uuid.UUID,
    ) -> None:
        service = await make_service(name="solo-service")
        await health_monitor_service.probe(
            organization_id, service.id, REACHABLE_URL, service_name=service.name
        )

        response = await client.get(
            "/gateway/health", params={"organization_id": str(organization_id)}
        )
        data = response.json()["data"]
        assert data["overall_status"] == "healthy"
        assert data["instances"][0]["circuit_state"] == "closed"
        assert data["instances"][0]["consecutive_failures"] == 0
