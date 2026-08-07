"""A minimal end-to-end smoke test, run once before dispatching the full test-writing pass.

Confirms the real app boots through its actual lifespan against real
PostgreSQL/Redis/RabbitMQ/MinIO, and that the core plugin lifecycle +
marketplace + installation + review paths all work end to end through
genuine HTTP requests.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_OK, AuthHeadersFn


def _checksummed_manifest() -> dict:
    manifest = {
        "name": "Smoke Test Plugin",
        "publisher": "smoke-tests",
        "category": "utilities",
        "type": "custom_plugin",
        "version": "1.0.0",
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["checksum"] = hashlib.sha256(canonical).hexdigest()
    return manifest


async def test_health_and_readiness(client: AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == HTTP_OK
    assert health.json()["data"]["status"] == "healthy"

    readiness = await client.get("/readiness")
    assert readiness.status_code == HTTP_OK
    assert readiness.json()["data"]["status"] == "ready"


async def test_full_plugin_lifecycle_end_to_end(
    client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
) -> None:
    headers = auth_headers(uuid.uuid4())
    params = {"organization_id": str(organization_id)}

    created = await client.post(
        "/plugins",
        params=params,
        json={
            "slug": "smoke-plugin",
            "name": "Smoke Plugin",
            "category": "utilities",
            "plugin_type": "custom_plugin",
        },
        headers=headers,
    )
    assert created.status_code == HTTP_CREATED, created.text
    plugin_id = created.json()["data"]["id"]

    manifest_response = await client.post(
        f"/plugins/{plugin_id}/manifest",
        params=params,
        json={"version_number": "1.0.0", "manifest": _checksummed_manifest()},
    )
    assert manifest_response.status_code == HTTP_CREATED, manifest_response.text
    assert manifest_response.json()["data"]["validation_status"] == "valid"

    published = await client.post(
        "/plugins/publish",
        params={**params, "plugin_id": plugin_id},
        json={"version_number": "1.0.0"},
    )
    assert published.status_code == HTTP_OK, published.text
    assert published.json()["data"]["status"] == "published"

    listing = await client.post(
        f"/plugins/marketplace-listings/{plugin_id}",
        params=params,
        json={"search_keywords": ["smoke"]},
    )
    assert listing.status_code == HTTP_CREATED, listing.text
    entry_id = listing.json()["data"]["id"]

    approved = await client.post(
        f"/plugins/marketplace-listings/{entry_id}/approve", params=params, headers=headers
    )
    assert approved.status_code == HTTP_OK, approved.text
    assert approved.json()["data"]["status"] == "published"

    found = await client.get("/plugins/marketplace", params={"query": "smoke"})
    assert found.status_code == HTTP_OK
    assert len(found.json()["data"]) == 1

    installed = await client.post(f"/plugins/{plugin_id}/install", params=params, json={})
    assert installed.status_code == HTTP_CREATED, installed.text
    assert installed.json()["data"]["status"] == "installed"

    activated = await client.post(f"/plugins/{plugin_id}/activate", params=params)
    assert activated.status_code == HTTP_OK, activated.text
    assert activated.json()["data"]["status"] == "active"

    reviewed = await client.post(
        "/plugins/reviews",
        params={**params, "plugin_id": plugin_id},
        json={"reviewer_id": "smoke-reviewer", "rating": 5, "body": "Works great."},
    )
    assert reviewed.status_code == HTTP_CREATED, reviewed.text

    reviews = await client.get("/plugins/reviews", params={"plugin_id": plugin_id})
    assert reviews.status_code == HTTP_OK
    assert len(reviews.json()["data"]) == 1

    statistics = await client.get("/plugins/statistics", params=params)
    assert statistics.status_code == HTTP_OK

    report = await client.post(
        "/plugins/reports", params={**params, "kind": "marketplace"}, headers=headers
    )
    assert report.status_code == HTTP_CREATED, report.text
    assert report.json()["data"]["status"] == "completed"
