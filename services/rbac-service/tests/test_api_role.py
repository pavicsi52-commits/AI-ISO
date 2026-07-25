"""HTTP-level tests for the ``/roles`` surface."""

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


async def test_list_roles_includes_seeded_roles(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.get("/roles", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 10


async def test_list_roles_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/roles")

    assert response.status_code == 401


async def test_create_role_requires_permission(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        "/roles", headers=headers, json={"name": "Hacker", "code": "hacker", "role_type": "custom"}
    )

    assert response.status_code == 403


async def test_create_role_as_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.post(
        "/roles",
        headers=headers,
        json={"name": "QA Lead", "code": f"qa-{uuid.uuid4().hex[:8]}", "role_type": "custom"},
    )

    assert response.status_code == 201
    assert response.json()["data"]["name"] == "QA Lead"


async def test_get_role_by_id(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    created = await client.post(
        "/roles",
        headers=headers,
        json={"name": "R", "code": f"r-{uuid.uuid4().hex[:8]}", "role_type": "custom"},
    )
    role_id = created.json()["data"]["id"]

    response = await client.get(f"/roles/{role_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == role_id


async def test_update_role(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    created = await client.post(
        "/roles",
        headers=headers,
        json={"name": "Original", "code": f"r-{uuid.uuid4().hex[:8]}", "role_type": "custom"},
    )
    role_id = created.json()["data"]["id"]

    response = await client.put(
        f"/roles/{role_id}",
        headers=headers,
        json={"name": "Updated", "status": "active", "priority": 5},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated"


async def test_delete_role(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    created = await client.post(
        "/roles",
        headers=headers,
        json={"name": "Temp", "code": f"r-{uuid.uuid4().hex[:8]}", "role_type": "custom"},
    )
    role_id = created.json()["data"]["id"]

    response = await client.delete(f"/roles/{role_id}", headers=headers)

    assert response.status_code == 200
    follow_up = await client.get(f"/roles/{role_id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_system_role_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.delete("/roles/00000000-0000-0000-0000-000000000101", headers=headers)

    assert response.status_code == 422


async def test_grant_and_revoke_permission(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    created = await client.post(
        "/roles",
        headers=headers,
        json={"name": "R", "code": f"r-{uuid.uuid4().hex[:8]}", "role_type": "custom"},
    )
    role_id = created.json()["data"]["id"]
    permissions = await client.get("/permissions", headers=headers)
    permission_id = next(p["id"] for p in permissions.json()["data"] if p["code"] == "reports:read")

    granted = await client.post(
        f"/roles/{role_id}/permissions", headers=headers, json={"permission_id": permission_id}
    )
    assert granted.status_code == 201

    revoked = await client.delete(f"/roles/{role_id}/permissions/{permission_id}", headers=headers)
    assert revoked.status_code == 200
