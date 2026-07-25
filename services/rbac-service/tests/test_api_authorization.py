"""HTTP-level tests for ``POST /authorization/evaluate``."""

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


async def test_evaluate_allows_platform_administrator(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin_id = uuid.uuid4()
    await make_platform_admin(db_session, admin_id)
    headers = auth_headers(admin_id)

    response = await client.post(
        "/authorization/evaluate",
        headers=headers,
        json={"user_id": str(admin_id), "action": "delete", "resource_type": "users"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "allow"


async def test_evaluate_denies_user_with_no_roles(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    subject_id = uuid.uuid4()

    response = await client.post(
        "/authorization/evaluate",
        headers=headers,
        json={"user_id": str(subject_id), "action": "delete", "resource_type": "users"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "deny"


async def test_evaluate_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/authorization/evaluate",
        json={"user_id": str(uuid.uuid4()), "action": "read", "resource_type": "users"},
    )

    assert response.status_code == 401


async def test_evaluate_after_role_assignment(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    subject_id = uuid.uuid4()
    await client.post(
        f"/users/{subject_id}/roles",
        headers=headers,
        json={"role_id": VIEWER_ROLE_ID, "scope_type": "global"},
    )

    response = await client.post(
        "/authorization/evaluate",
        headers=headers,
        json={"user_id": str(subject_id), "action": "read", "resource_type": "users"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "allow"
    assert response.json()["data"]["matched_permission_code"] == "users:read"
