"""HTTP-level tests for the ``/permissions`` surface."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_platform_admin


async def _admin_headers(
    db_session: AsyncSession, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> dict[str, str]:
    admin_id = uuid.uuid4()
    await make_platform_admin(db_session, admin_id)
    return auth_headers(admin_id)


async def test_list_permissions_includes_seeded_catalog(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.get("/permissions", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 320


async def test_create_permission_requires_permission(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        "/permissions",
        headers=headers,
        json={
            "name": "Custom",
            "code": "custom:read",
            "resource": "reports",
            "action": "read",
        },
    )

    assert response.status_code == 403


async def test_create_update_delete_permission(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    created = await client.post(
        "/permissions",
        headers=headers,
        json={
            "name": "Custom",
            "code": f"custom-{uuid.uuid4().hex[:8]}",
            "resource": "reports",
            "action": "read",
        },
    )
    assert created.status_code == 201
    permission_id = created.json()["data"]["id"]

    updated = await client.put(
        f"/permissions/{permission_id}",
        headers=headers,
        json={"name": "Renamed", "status": "active"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Renamed"

    deleted = await client.delete(f"/permissions/{permission_id}", headers=headers)
    assert deleted.status_code == 200
