"""A minimal end-to-end smoke test, run once before dispatching the full test-writing pass.

Confirms the real app boots through its actual lifespan against real
PostgreSQL/Redis/RabbitMQ, and that the core connector lifecycle +
marketplace + transformation + flow + statistics/audit paths all work
end to end through genuine HTTP requests.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_OK, AuthHeadersFn


async def test_health_and_readiness(client: AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == HTTP_OK
    assert health.json()["data"]["status"] == "healthy"

    readiness = await client.get("/readiness")
    assert readiness.status_code == HTTP_OK
    assert readiness.json()["data"]["status"] == "ready"


async def test_full_connector_lifecycle_end_to_end(
    client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
) -> None:
    headers = auth_headers(uuid.uuid4())
    params = {"organization_id": str(organization_id)}

    created = await client.post(
        "/integrations/connectors",
        params=params,
        json={"name": "smoke-connector", "category": "custom", "connector_type": "rest_api"},
        headers=headers,
    )
    assert created.status_code == HTTP_CREATED, created.text
    connector_id = created.json()["data"]["id"]

    configured = await client.put(
        f"/integrations/connectors/{connector_id}",
        params=params,
        json={"config": {"endpoint_url": "https://example.com"}},
        headers=headers,
    )
    assert configured.status_code == HTTP_OK, configured.text

    enabled = await client.post(
        f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
    )
    assert enabled.status_code == HTTP_OK
    assert enabled.json()["data"]["enabled"] is True

    synced = await client.post(
        f"/integrations/connectors/{connector_id}/sync",
        params=params,
        json={"records": [{"id": 1}, {"id": 2}]},
        headers=headers,
    )
    assert synced.status_code == HTTP_OK, synced.text
    assert synced.json()["data"]["records_succeeded"] == 2

    categories = await client.get("/integrations/categories", params=params)
    assert categories.status_code == HTTP_OK
    assert len(categories.json()["data"]) == 15

    marketplace = await client.get("/integrations/marketplace", params=params)
    assert marketplace.status_code == HTTP_OK
    assert len(marketplace.json()["data"]) > 50

    audit = await client.get("/integrations/audit", params=params)
    assert audit.status_code == HTTP_OK
    assert len(audit.json()["data"]) >= 2
