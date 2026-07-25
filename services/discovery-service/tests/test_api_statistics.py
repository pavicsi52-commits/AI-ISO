"""Tests for ``GET /discovery/statistics`` against the real app lifespan."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import seed_job


async def test_get_statistics_recomputes_when_no_snapshot_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    org_id = uuid.uuid4()
    await seed_job(db_session, organization_id=org_id)
    await db_session.commit()

    headers = auth_headers(uuid.uuid4())
    response = await client.get(
        "/discovery/statistics", params={"organization_id": str(org_id)}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["total_jobs"] == 1


async def test_get_statistics_for_org_with_no_activity(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.get(
        "/discovery/statistics", params={"organization_id": str(uuid.uuid4())}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["total_jobs"] == 0
