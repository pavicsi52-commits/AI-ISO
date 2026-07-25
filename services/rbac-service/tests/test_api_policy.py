"""HTTP-level tests for the ``/policies`` surface."""

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


async def test_create_policy_with_conditions(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)

    response = await client.post(
        "/policies",
        headers=headers,
        json={
            "name": "Business Hours",
            "code": f"biz-{uuid.uuid4().hex[:8]}",
            "effect": "allow",
            "resource_type": "reports",
            "action": "read",
            "priority": 100,
            "conditions": [
                {"condition_type": "time_based", "value": {"start_hour": 9, "end_hour": 17}}
            ],
            "subject_type": "global",
        },
    )

    assert response.status_code == 201
    assert len(response.json()["data"]["conditions"]) == 1


async def test_create_policy_requires_permission(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())

    response = await client.post(
        "/policies", headers=headers, json={"name": "X", "code": "x", "subject_type": "global"}
    )

    assert response.status_code == 403


async def test_list_update_delete_policy(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    headers = await _admin_headers(db_session, auth_headers)
    created = await client.post(
        "/policies",
        headers=headers,
        json={"name": "P", "code": f"p-{uuid.uuid4().hex[:8]}", "subject_type": "global"},
    )
    policy_id = created.json()["data"]["id"]

    listed = await client.get("/policies", headers=headers)
    assert policy_id in {p["id"] for p in listed.json()["data"]}

    updated = await client.put(
        f"/policies/{policy_id}",
        headers=headers,
        json={"name": "P Renamed", "effect": "deny", "priority": 50, "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "P Renamed"

    deleted = await client.delete(f"/policies/{policy_id}", headers=headers)
    assert deleted.status_code == 200
