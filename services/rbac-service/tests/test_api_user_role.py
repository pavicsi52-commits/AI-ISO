"""HTTP-level tests for ``/users/{id}/roles`` and ``/users/{id}/permissions``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_platform_admin

VIEWER_ROLE_ID = "00000000-0000-0000-0000-000000000107"


async def _admin_headers(
    db_session: AsyncSession, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> dict[str, str]:
    admin_id = uuid.uuid4()
    await make_platform_admin(db_session, admin_id)
    return auth_headers(admin_id)


async def test_assign_and_list_permissions(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    target_user = uuid.uuid4()

    assigned = await client.post(
        f"/users/{target_user}/roles",
        headers=headers,
        json={"role_id": VIEWER_ROLE_ID, "scope_type": "global"},
    )
    assert assigned.status_code == 201

    permissions = await client.get(f"/users/{target_user}/permissions", headers=headers)
    assert permissions.status_code == 200
    assert "users:read" in permissions.json()["data"]["permissions"]
    assert permissions.json()["data"]["role_codes"] == ["viewer"]


async def test_assign_role_requires_permission(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        f"/users/{uuid.uuid4()}/roles",
        headers=headers,
        json={"role_id": VIEWER_ROLE_ID, "scope_type": "global"},
    )

    assert response.status_code == 403


async def test_assign_organization_scoped_role_requires_scope_id(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.post(
        f"/users/{uuid.uuid4()}/roles",
        headers=headers,
        json={"role_id": VIEWER_ROLE_ID, "scope_type": "organization"},
    )

    # shared_core.exceptions standardizes every validation failure (Pydantic's
    # own RequestValidationError included) to 400, not FastAPI's default 422.
    assert response.status_code == 400


async def test_remove_role(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    target_user = uuid.uuid4()
    await client.post(
        f"/users/{target_user}/roles",
        headers=headers,
        json={"role_id": VIEWER_ROLE_ID, "scope_type": "global"},
    )

    removed = await client.delete(f"/users/{target_user}/roles/{VIEWER_ROLE_ID}", headers=headers)

    assert removed.status_code == 200
    permissions = await client.get(f"/users/{target_user}/permissions", headers=headers)
    assert permissions.json()["data"]["permissions"] == []


async def test_get_permissions_for_user_with_no_roles(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.get(f"/users/{uuid.uuid4()}/permissions", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == []
