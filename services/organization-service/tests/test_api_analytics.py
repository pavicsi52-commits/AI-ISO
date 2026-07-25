"""Tests for ``app/api/analytics.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import add_member, make_org_with_owner

from app.models.enums import MemberRole


async def test_get_analytics_counts_real_members(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    await add_member(db_session, organization.id, uuid.uuid4(), role=MemberRole.MEMBER)
    await add_member(db_session, organization.id, uuid.uuid4(), role=MemberRole.MEMBER)

    response = await client.get(
        f"/organizations/{organization.id}/analytics", headers=auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user_count"] == 3
    assert body["project_count"] == 0
    assert body["asset_count"] == 0


async def test_get_analytics_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/analytics", headers=auth_headers(outsider)
    )
    assert response.status_code == 403
