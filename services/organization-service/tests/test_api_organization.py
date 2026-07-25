"""Tests for ``app/api/organization.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org, make_org_with_owner


async def test_create_organization_makes_caller_owner(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/organizations",
        json={"name": "Acme Corp", "slug": f"acme-{caller.hex[:8]}"},
        headers=auth_headers(caller),
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"] == "Acme Corp"
    assert body["status"] == "pending"

    org_id = body["id"]
    get_response = await client.get(f"/organizations/{org_id}", headers=auth_headers(caller))
    assert get_response.status_code == 200


async def test_create_organization_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/organizations", json={"name": "No Auth", "slug": "no-auth"})
    assert response.status_code == 401


async def test_create_organization_duplicate_slug_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    headers = auth_headers(caller)
    payload = {"name": "First", "slug": f"dup-{caller.hex[:8]}"}
    first = await client.post("/organizations", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post(
        "/organizations", json={"name": "Second", "slug": payload["slug"]}, headers=headers
    )
    assert second.status_code == 409


async def test_list_organizations_any_authenticated_caller(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    await make_org(db_session, name="Directory Org")
    outsider = uuid.uuid4()
    response = await client.get("/organizations", headers=auth_headers(outsider))
    assert response.status_code == 200
    names = {org["name"] for org in response.json()["data"]}
    assert "Directory Org" in names


async def test_get_organization_not_found(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(
        f"/organizations/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_update_organization_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/organizations/{organization.id}",
        json={"name": "Renamed"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/organizations/{organization.id}",
        json={"name": "Renamed", "status": "active"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["name"] == "Renamed"
    assert allowed.json()["data"]["status"] == "active"


async def test_delete_organization_requires_admin_then_soft_deletes(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.delete(
        f"/organizations/{organization.id}", headers=auth_headers(outsider)
    )
    assert forbidden.status_code == 403

    allowed = await client.delete(f"/organizations/{organization.id}", headers=auth_headers(owner))
    assert allowed.status_code == 200

    after = await client.get(f"/organizations/{organization.id}", headers=auth_headers(owner))
    assert after.status_code == 404
