"""Tests for ``/discovery/schedules`` against the real app lifespan,
including live registration with the real
:class:`~shared_core.scheduler.SchedulerManager`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def _create_profile(
    client: AsyncClient, headers: dict[str, str], *, organization_id: uuid.UUID
) -> str:
    resp = await client.post(
        "/discovery/profiles",
        json={
            "organization_id": str(organization_id),
            "name": f"schedule-profile-{uuid.uuid4()}",
            "profile_type": "custom",
            "protocols": ["tcp"],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def test_create_update_delete_schedule(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()
    profile_id = await _create_profile(client, headers, organization_id=org_id)

    create_resp = await client.post(
        "/discovery/schedules",
        json={
            "organization_id": str(org_id),
            "profile_id": profile_id,
            "name": f"api-schedule-{uuid.uuid4()}",
            "schedule_type": "interval",
            "interval_seconds": 3600,
            "priority": 5,
            "concurrency_limit": 1,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    schedule = create_resp.json()["data"]
    assert schedule["schedule_type"] == "interval"
    assert schedule["is_enabled"] is True
    schedule_id = schedule["id"]

    list_resp = await client.get(
        "/discovery/schedules", params={"organization_id": str(org_id)}, headers=headers
    )
    assert list_resp.status_code == 200
    assert any(item["id"] == schedule_id for item in list_resp.json()["data"])

    update_resp = await client.put(
        f"/discovery/schedules/{schedule_id}",
        json={
            "name": "renamed-schedule",
            "schedule_type": "interval",
            "interval_seconds": 7200,
            "is_enabled": True,
            "priority": 7,
            "concurrency_limit": 2,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["data"]["interval_seconds"] == 7200

    deactivate_resp = await client.put(
        f"/discovery/schedules/{schedule_id}",
        json={
            "name": "renamed-schedule",
            "schedule_type": "interval",
            "interval_seconds": 7200,
            "is_enabled": False,
            "priority": 7,
            "concurrency_limit": 2,
        },
        headers=headers,
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["data"]["is_enabled"] is False

    delete_resp = await client.delete(f"/discovery/schedules/{schedule_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["success"] is True


async def test_create_cron_schedule(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()
    profile_id = await _create_profile(client, headers, organization_id=org_id)

    create_resp = await client.post(
        "/discovery/schedules",
        json={
            "organization_id": str(org_id),
            "profile_id": profile_id,
            "name": f"cron-schedule-{uuid.uuid4()}",
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    assert create_resp.json()["data"]["cron_expression"] == "0 * * * *"


async def test_delete_unknown_schedule_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.delete(f"/discovery/schedules/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
