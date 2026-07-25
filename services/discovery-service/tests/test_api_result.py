"""Tests for ``GET /discovery/results`` against the real app lifespan."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import seed_job, seed_result, seed_target


async def test_list_results_for_job(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    org_id = uuid.uuid4()
    job = await seed_job(db_session, organization_id=org_id)
    target = await seed_target(db_session, organization_id=org_id)
    await seed_result(db_session, organization_id=org_id, job_id=job.id, target_id=target.id)
    await db_session.commit()

    headers = auth_headers(uuid.uuid4())
    response = await client.get(
        "/discovery/results", params={"job_id": str(job.id)}, headers=headers
    )
    assert response.status_code == 200, response.text
    results = response.json()["data"]
    assert len(results) == 1
    assert results[0]["job_id"] == str(job.id)
    assert results[0]["status"] == "success"


async def test_list_results_for_unknown_job_is_empty(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.get(
        "/discovery/results", params={"job_id": str(uuid.uuid4())}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
