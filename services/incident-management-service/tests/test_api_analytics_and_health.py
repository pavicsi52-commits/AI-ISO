"""HTTP tests for statistics, reports, audit, and health routes."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _open_incident(client: AsyncClient, headers: dict[str, str], organization_id) -> dict:
    resp = await client.post(
        "/incidents",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json={"title": "Something broke"},
    )
    assert resp.status_code == HTTP_CREATED
    return resp.json()["data"]


class TestHealth:
    async def test_health(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "healthy"

    async def test_liveness(self, client: AsyncClient) -> None:
        resp = await client.get("/liveness")
        assert resp.status_code == HTTP_OK

    async def test_readiness(self, client: AsyncClient) -> None:
        resp = await client.get("/readiness")
        assert resp.status_code == HTTP_OK

    async def test_metrics(self, client: AsyncClient) -> None:
        resp = await client.get("/metrics")
        assert resp.status_code == HTTP_OK


class TestStatistics:
    async def test_dashboard(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        resp = await client.get(
            "/statistics/dashboard", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert "by_status" in resp.json()["data"]

    async def test_rollup(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        now = "2026-01-01T00:00:00Z"
        later = "2026-01-02T00:00:00Z"
        resp = await client.post(
            "/statistics/rollup",
            params={"organization_id": str(organization_id)},
            json={"window_start": now, "window_end": later},
        )
        assert resp.status_code == HTTP_CREATED

    async def test_trend(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        resp = await client.get(
            "/statistics/trend", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert isinstance(resp.json()["data"], list)


class TestReports:
    async def test_generate_list_and_get(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        generated = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "incident"},
        )
        assert generated.status_code == HTTP_CREATED
        report_id = generated.json()["data"]["id"]

        listed = await client.get("/reports", params={"organization_id": str(organization_id)})
        assert report_id in {one["id"] for one in listed.json()["data"]}

        fetched = await client.get(
            f"/reports/{report_id}", params={"organization_id": str(organization_id)}
        )
        assert fetched.status_code == HTTP_OK

    async def test_download_csv(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        generated = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "incident", "report_format": "csv"},
        )
        report_id = generated.json()["data"]["id"]
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert "reference" in resp.text

    async def test_download_markdown(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        generated = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "incident", "report_format": "markdown"},
        )
        report_id = generated.json()["data"]["id"]
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert "|" in resp.text

    async def test_download_json(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        generated = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "incident"},
        )
        report_id = generated.json()["data"]["id"]
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is not None


class TestAudit:
    async def test_list_finds_the_creation_entry(
        self, client: AsyncClient, auth_headers, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        resp = await client.get("/audit", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) >= 1

    async def test_summary(self, client: AsyncClient, auth_headers, organization_id) -> None:
        headers = auth_headers(uuid.uuid4())
        await _open_incident(client, headers, organization_id)
        resp = await client.get("/audit/summary", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["total"] >= 1
