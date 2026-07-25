"""Tests for ``app/api/search.py``, ``app/api/statistics.py``, and
``app/api/analytics.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_search_by_query_and_filters(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    await client.post(
        "/inventory/assets",
        json={
            "organization_id": str(org_id),
            "name": "alpha",
            "hostname": "alpha.internal",
            "asset_type": "database",
            "status": "discovered",
        },
        headers=headers,
    )
    await client.post(
        "/inventory/assets",
        json={
            "organization_id": str(org_id),
            "name": "beta",
            "hostname": "beta.internal",
            "asset_type": "virtual_machine",
        },
        headers=headers,
    )

    response = await client.get(
        f"/inventory/search?organization_id={org_id}&q=alpha", headers=headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["name"] == "alpha"

    filtered = await client.get(
        f"/inventory/search?organization_id={org_id}&asset_type=database&status=discovered",
        headers=headers,
    )
    assert filtered.json()["data"]["pagination"]["total"] == 1

    sorted_response = await client.get(
        f"/inventory/search?organization_id={org_id}&sort=name:asc&page=1&page_size=1",
        headers=headers,
    )
    assert sorted_response.status_code == 200
    assert len(sorted_response.json()["data"]["items"]) == 1


async def test_search_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/search?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


async def test_statistics_and_analytics(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    await client.post(
        "/inventory/assets",
        json={"organization_id": str(org_id), "name": "asset-1", "asset_type": "database"},
        headers=headers,
    )

    statistics_response = await client.get(
        f"/inventory/statistics?organization_id={org_id}", headers=headers
    )
    assert statistics_response.status_code == 200
    assert statistics_response.json()["data"]["total_assets"] == 1

    analytics_response = await client.get(
        f"/inventory/analytics?organization_id={org_id}", headers=headers
    )
    assert analytics_response.status_code == 200
    body = analytics_response.json()["data"]
    assert body["total_assets"] == 1
    assert "discovery_source_distribution" in body
    assert "assets_added_last_30_days" in body


async def test_statistics_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/statistics?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


async def test_analytics_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/inventory/analytics?organization_id={uuid.uuid4()}")
    assert response.status_code == 401


__all__: list[str] = []
