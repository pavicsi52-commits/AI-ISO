"""HTTP-level tests for ``app/api/marketplace.py`` (``/plugins/marketplace-listings``).

Distinct from ``GET /plugins/marketplace``, the public search route, which
lives in ``app/api/plugins.py`` and belongs to a different test file.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
)


async def _register_plugin(
    client: AsyncClient,
    organization_id: uuid.UUID,
    auth_headers: AuthHeadersFn,
    *,
    slug: str = "listing-plugin",
) -> str:
    response = await client.post(
        "/plugins",
        params={"organization_id": str(organization_id)},
        json={
            "slug": slug,
            "name": "Listing Plugin",
            "category": "utilities",
            "plugin_type": "custom_plugin",
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == HTTP_CREATED, response.text
    return response.json()["data"]["id"]


async def _create_listing(
    client: AsyncClient, organization_id: uuid.UUID, plugin_id: str, **body
) -> dict:
    response = await client.post(
        f"/plugins/marketplace-listings/{plugin_id}",
        params={"organization_id": str(organization_id)},
        json=body,
    )
    assert response.status_code == HTTP_CREATED, response.text
    return response.json()["data"]


async def test_create_listing_draft_defaults(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="draft-defaults")
    listing = await _create_listing(client, organization_id, plugin_id)

    assert listing["plugin_id"] == plugin_id
    assert listing["status"] == "draft"
    assert listing["featured"] is False
    assert listing["search_keywords"] == []
    assert listing["install_count"] == 0
    assert listing["active_install_count"] == 0


async def test_create_listing_with_full_body(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="draft-full")
    listing = await _create_listing(
        client,
        organization_id,
        plugin_id,
        search_keywords=["automation", "widgets"],
        icon_url="https://cdn.example/icon.png",
        screenshots=["https://cdn.example/1.png", "https://cdn.example/2.png"],
        pricing_summary="Free",
    )

    assert listing["search_keywords"] == ["automation", "widgets"]
    assert listing["icon_url"] == "https://cdn.example/icon.png"
    assert listing["pricing_summary"] == "Free"


async def test_create_duplicate_listing_returns_error(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="dup-listing")
    await _create_listing(client, organization_id, plugin_id)

    dup = await client.post(
        f"/plugins/marketplace-listings/{plugin_id}",
        params={"organization_id": str(organization_id)},
        json={},
    )
    assert dup.status_code >= HTTP_BAD_REQUEST, dup.text
    assert dup.status_code == HTTP_BAD_REQUEST


async def test_list_pending_includes_fresh_draft(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="pending-plugin")
    listing = await _create_listing(client, organization_id, plugin_id)

    pending = await client.get("/plugins/marketplace-listings/pending")
    assert pending.status_code == HTTP_OK, pending.text
    ids = {row["id"] for row in pending.json()["data"]}
    assert listing["id"] in ids
    for row in pending.json()["data"]:
        assert row["status"] == "draft"


async def test_list_pending_respects_limit(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    for i in range(3):
        plugin_id = await _register_plugin(
            client, organization_id, auth_headers, slug=f"pending-limit-{i}"
        )
        await _create_listing(client, organization_id, plugin_id)

    pending = await client.get("/plugins/marketplace-listings/pending", params={"limit": 1})
    assert pending.status_code == HTTP_OK, pending.text
    assert len(pending.json()["data"]) <= 1


async def test_approve_listing_requires_auth(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="approve-noauth")
    listing = await _create_listing(client, organization_id, plugin_id)

    response = await client.post(
        f"/plugins/marketplace-listings/{listing['id']}/approve",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_UNAUTHORIZED


async def test_approve_listing_publishes(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="approve-plugin")
    listing = await _create_listing(client, organization_id, plugin_id)
    headers = auth_headers(uuid.uuid4())

    approved = await client.post(
        f"/plugins/marketplace-listings/{listing['id']}/approve",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert approved.status_code == HTTP_OK, approved.text
    assert approved.json()["data"]["status"] == "published"


async def test_approve_listing_not_found(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.post(
        f"/plugins/marketplace-listings/{uuid.uuid4()}/approve",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_reject_listing_transitions_to_removed(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    # A separate listing from the one used in the approve test, so the two
    # status transitions cannot interfere with one another.
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="reject-plugin")
    listing = await _create_listing(client, organization_id, plugin_id)

    rejected = await client.post(
        f"/plugins/marketplace-listings/{listing['id']}/reject",
        json={"reason": "Fails content policy."},
    )
    assert rejected.status_code == HTTP_OK, rejected.text
    assert rejected.json()["data"]["status"] == "removed"


async def test_reject_listing_not_found(client: AsyncClient) -> None:
    response = await client.post(
        f"/plugins/marketplace-listings/{uuid.uuid4()}/reject",
        json={"reason": "Does not exist."},
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_feature_and_unfeature_listing(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(client, organization_id, auth_headers, slug="feature-plugin")
    listing = await _create_listing(client, organization_id, plugin_id)
    headers = auth_headers(uuid.uuid4())

    approved = await client.post(
        f"/plugins/marketplace-listings/{listing['id']}/approve",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert approved.status_code == HTTP_OK, approved.text
    assert approved.json()["data"]["status"] == "published"

    featured = await client.post(f"/plugins/marketplace-listings/{listing['id']}/feature")
    assert featured.status_code == HTTP_OK, featured.text
    assert featured.json()["data"]["status"] == "featured"
    assert featured.json()["data"]["featured"] is True

    unfeatured = await client.post(f"/plugins/marketplace-listings/{listing['id']}/unfeature")
    assert unfeatured.status_code == HTTP_OK, unfeatured.text
    assert unfeatured.json()["data"]["status"] == "published"
    assert unfeatured.json()["data"]["featured"] is False


async def test_feature_listing_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/plugins/marketplace-listings/{uuid.uuid4()}/feature")
    assert response.status_code == HTTP_NOT_FOUND


async def test_unfeature_listing_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/plugins/marketplace-listings/{uuid.uuid4()}/unfeature")
    assert response.status_code == HTTP_NOT_FOUND


async def test_deprecate_listing(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_plugin(
        client, organization_id, auth_headers, slug="deprecate-plugin"
    )
    listing = await _create_listing(client, organization_id, plugin_id)
    headers = auth_headers(uuid.uuid4())

    approved = await client.post(
        f"/plugins/marketplace-listings/{listing['id']}/approve",
        params={"organization_id": str(organization_id)},
        headers=headers,
    )
    assert approved.status_code == HTTP_OK, approved.text

    deprecated = await client.post(f"/plugins/marketplace-listings/{listing['id']}/deprecate")
    assert deprecated.status_code == HTTP_OK, deprecated.text
    assert deprecated.json()["data"]["status"] == "deprecated"


async def test_deprecate_listing_not_found(client: AsyncClient) -> None:
    response = await client.post(f"/plugins/marketplace-listings/{uuid.uuid4()}/deprecate")
    assert response.status_code == HTTP_NOT_FOUND


__all__: list[str] = []
