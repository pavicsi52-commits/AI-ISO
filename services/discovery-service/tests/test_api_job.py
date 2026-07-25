"""Tests for ``/discovery/jobs`` against the real app lifespan.

Only covers the REST-layer contract (creation, listing, lookup,
cancellation) -- actual job *execution* correctness (worker completing
a job, cross-session visibility) is covered by ``tests/test_workers.py``,
which invokes the worker handler directly against a real, non-SAVEPOINT
session (this file's ``client`` fixture uses an overridden SAVEPOINT
session the independently-connected async worker could never see).
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
            "name": f"job-profile-{uuid.uuid4()}",
            "profile_type": "custom",
            "protocols": ["tcp"],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def test_create_get_list_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()
    profile_id = await _create_profile(client, headers, organization_id=org_id)

    create_resp = await client.post(
        "/discovery/jobs",
        json={"organization_id": str(org_id), "profile_id": profile_id, "mode": "manual"},
        headers=headers,
    )
    assert create_resp.status_code == 202, create_resp.text
    job = create_resp.json()["data"]
    assert job["status"] == "queued"
    assert job["profile_id"] == profile_id
    job_id = job["id"]

    get_resp = await client.get(f"/discovery/jobs/{job_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == job_id

    list_resp = await client.get(
        "/discovery/jobs", params={"organization_id": str(org_id)}, headers=headers
    )
    assert list_resp.status_code == 200
    assert any(item["id"] == job_id for item in list_resp.json()["data"])


async def test_get_unknown_job_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.get(f"/discovery/jobs/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


async def test_cancel_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()
    profile_id = await _create_profile(client, headers, organization_id=org_id)

    create_resp = await client.post(
        "/discovery/jobs",
        json={"organization_id": str(org_id), "profile_id": profile_id, "mode": "manual"},
        headers=headers,
    )
    job_id = create_resp.json()["data"]["id"]

    cancel_resp = await client.delete(f"/discovery/jobs/{job_id}", headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert cancel_resp.json()["data"]["status"] == "cancelled"

    second_cancel = await client.delete(f"/discovery/jobs/{job_id}", headers=headers)
    assert second_cancel.status_code == 409
