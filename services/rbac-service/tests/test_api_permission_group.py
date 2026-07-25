"""HTTP-level tests for the ``/permission-groups`` surface."""

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


async def test_create_and_list_permission_group(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    created = await client.post(
        "/permission-groups",
        headers=headers,
        json={
            "name": "Infrastructure",
            "code": f"infra-{uuid.uuid4().hex[:8]}",
            "category": "infrastructure",
        },
    )
    assert created.status_code == 201

    listed = await client.get("/permission-groups", headers=headers)
    assert listed.status_code == 200
    assert created.json()["data"]["id"] in {g["id"] for g in listed.json()["data"]}


async def test_create_permission_group_requires_permission(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        "/permission-groups", headers=headers, json={"name": "X", "code": "x"}
    )

    assert response.status_code == 403
