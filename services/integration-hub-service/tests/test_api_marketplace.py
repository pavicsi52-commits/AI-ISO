"""HTTP tests for /integrations/marketplace.

Only `publish` declares a `caller: CurrentUserId` dependency -- it records
who published the entry and writes an audit entry. `list`/`get`/`rate`
take no `CurrentUserId` dependency at all -- confirmed by reading
`app/api/marketplace.py` directly, not assumed.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import ConnectorCategory
from app.services.marketplace import _BUILTIN_CONNECTORS
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
)

pytestmark = pytest.mark.asyncio

_EXPECTED_BUILTIN_COUNT = sum(len(names) for names in _BUILTIN_CONNECTORS.values())


async def _publish(
    client: AsyncClient,
    auth_headers: AuthHeadersFn,
    organization_id: uuid.UUID,
    *,
    slug: str,
    **overrides: object,
) -> dict:
    payload = {"slug": slug, "name": slug, "category": "custom", **overrides}
    resp = await client.post(
        "/integrations/marketplace/publish",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestListMarketplace:
    async def test_first_call_seeds_the_builtin_catalog(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/integrations/marketplace",
            params={"organization_id": str(organization_id), "limit": 1000},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert _EXPECTED_BUILTIN_COUNT >= 70
        assert len(data) == _EXPECTED_BUILTIN_COUNT
        assert all(row["built_in"] is True for row in data)

    async def test_second_call_does_not_duplicate_the_seed(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        first = await client.get(
            "/integrations/marketplace",
            params={"organization_id": str(organization_id), "limit": 1000},
        )
        second = await client.get(
            "/integrations/marketplace",
            params={"organization_id": str(organization_id), "limit": 1000},
        )
        assert len(first.json()["data"]) == len(second.json()["data"]) == _EXPECTED_BUILTIN_COUNT

    async def test_filters_by_category(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/integrations/marketplace",
            params={"organization_id": str(organization_id), "category": "cloud", "limit": 1000},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert len(data) == len(_BUILTIN_CONNECTORS[ConnectorCategory.CLOUD])
        assert all(row["category"] == "cloud" for row in data)

    async def test_is_scoped_per_organization(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.get(
            "/integrations/marketplace", params={"organization_id": str(organization_id)}
        )
        other_org = uuid.uuid4()
        other_resp = await client.get(
            "/integrations/marketplace", params={"organization_id": str(other_org), "limit": 1000}
        )
        assert other_resp.status_code == HTTP_OK
        # A fresh organization seeds its own full catalog independently.
        assert len(other_resp.json()["data"]) == _EXPECTED_BUILTIN_COUNT


class TestGetEntry:
    async def test_get_returns_a_seeded_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        listed = await client.get(
            "/integrations/marketplace", params={"organization_id": str(organization_id)}
        )
        entry_id = listed.json()["data"][0]["id"]
        resp = await client.get(
            f"/integrations/marketplace/{entry_id}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == entry_id

    async def test_get_returns_404_for_a_missing_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/marketplace/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_isolated_across_organizations(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        listed = await client.get(
            "/integrations/marketplace", params={"organization_id": str(organization_id)}
        )
        entry_id = listed.json()["data"][0]["id"]
        other_org = uuid.uuid4()
        resp = await client.get(
            f"/integrations/marketplace/{entry_id}", params={"organization_id": str(other_org)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestPublish:
    async def test_publish_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/marketplace/publish",
            params={"organization_id": str(organization_id)},
            json={"slug": "no-auth", "name": "No Auth", "category": "custom"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_publish_creates_a_new_entry(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        data = await _publish(
            client,
            auth_headers,
            organization_id,
            slug="acme-connector",
            name="Acme Connector",
            version_number="1.2.3",
        )
        assert data["slug"] == "acme-connector"
        assert data["built_in"] is False
        assert data["latest_version_number"] == "1.2.3"

    async def test_publish_duplicate_slug_is_a_bad_request(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        await _publish(client, auth_headers, organization_id, slug="dup-http", name="Dup")
        second = await client.post(
            "/integrations/marketplace/publish",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"slug": "dup-http", "name": "Dup Again", "category": "custom"},
        )
        assert second.status_code == HTTP_BAD_REQUEST

    async def test_publish_with_a_missing_dependency_is_a_bad_request(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/marketplace/publish",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "slug": "needs-dep",
                "name": "Needs Dep",
                "category": "custom",
                "dependencies": ["missing-dep"],
            },
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_publish_with_an_already_published_dependency_succeeds(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        await _publish(client, auth_headers, organization_id, slug="base-http", name="Base")
        resp = await client.post(
            "/integrations/marketplace/publish",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "slug": "depends-on-base-http",
                "name": "Depends",
                "category": "custom",
                "dependencies": ["base-http"],
            },
        )
        assert resp.status_code == HTTP_CREATED

    async def test_publish_records_an_audit_entry(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        await _publish(client, auth_headers, organization_id, slug="audited", name="Audited")
        audit = await client.get(
            "/integrations/audit", params={"organization_id": str(organization_id)}
        )
        assert audit.status_code == HTTP_OK
        actions = {row["action"] for row in audit.json()["data"]}
        assert "marketplace_published" in actions


class TestRate:
    async def test_rate_does_not_require_auth(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _publish(
            client, auth_headers, organization_id, slug="rateable-http", name="Rateable"
        )
        resp = await client.post(
            f"/integrations/marketplace/{created['id']}/rate",
            params={"organization_id": str(organization_id)},
            json={"rating": 4.5},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["rating_count"] == 1

    async def test_rate_accumulates_across_calls(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _publish(
            client, auth_headers, organization_id, slug="rated-twice", name="Rated Twice"
        )
        await client.post(
            f"/integrations/marketplace/{created['id']}/rate",
            params={"organization_id": str(organization_id)},
            json={"rating": 3.0},
        )
        second = await client.post(
            f"/integrations/marketplace/{created['id']}/rate",
            params={"organization_id": str(organization_id)},
            json={"rating": 5.0},
        )
        assert second.json()["data"]["rating_count"] == 2

    async def test_rate_out_of_range_is_rejected_by_schema_validation(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        created = await _publish(
            client, auth_headers, organization_id, slug="bad-rating", name="Bad Rating"
        )
        resp = await client.post(
            f"/integrations/marketplace/{created['id']}/rate",
            params={"organization_id": str(organization_id)},
            json={"rating": 0.5},
        )
        # `MarketplaceRateRequest.rating` already declares `ge=1.0, le=5.0`
        # at the Pydantic level, so an out-of-range value never reaches
        # `MarketplaceService.rate`'s own `ValidationError` -- it's FastAPI's
        # own 422 request-validation error, but `RequestValidationMiddleware`
        # remaps that onto this platform's own `ValidationError` shape
        # (`shared_core.exceptions.validation.ValidationError.status_code
        # == 400`), the same remap every other AI-IOS service's own test
        # suite already documents -- never FastAPI's raw 422 default.
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_rate_returns_404_for_a_missing_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/marketplace/{uuid.uuid4()}/rate",
            params={"organization_id": str(organization_id)},
            json={"rating": 3.0},
        )
        assert resp.status_code == HTTP_NOT_FOUND
