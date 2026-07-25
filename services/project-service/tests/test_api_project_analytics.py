"""Tests for ``app/api/project_analytics.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import ADMINISTRATOR_ROLE_ID
from tests.conftest import add_member, make_project_with_owner


async def test_get_analytics_counts_real_members(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)
    await add_member(
        db_session, project.id, project.organization_id, uuid.uuid4(), role_id=ADMINISTRATOR_ROLE_ID
    )

    response = await client.get(f"/projects/{project.id}/analytics", headers=auth_headers(owner))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["member_count"] == 2
    assert body["automation_count"] == 0
    assert body["workflow_count"] == 0


async def test_get_analytics_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    response = await client.get(f"/projects/{project.id}/analytics", headers=auth_headers(outsider))
    assert response.status_code == 403
