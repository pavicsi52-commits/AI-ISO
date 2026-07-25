"""Tests for ``app/api/organization_quota.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner

_QUOTA_PAYLOAD = {
    "max_users": 25,
    "max_projects": 10,
    "max_assets": 2000,
    "max_storage_gb": 100,
    "max_workflows": 40,
    "max_automation_jobs": 100,
    "max_connectors": 20,
    "max_api_calls_per_day": 20000,
    "max_ai_requests_per_day": 2000,
    "max_plugins": 20,
}


async def test_get_quotas_creates_defaults(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/quotas", headers=auth_headers(owner)
    )
    assert response.status_code == 200
    assert response.json()["data"]["max_users"] == 10


async def test_get_quotas_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/quotas", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


async def test_update_quotas_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/organizations/{organization.id}/quotas",
        json=_QUOTA_PAYLOAD,
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/organizations/{organization.id}/quotas", json=_QUOTA_PAYLOAD, headers=auth_headers(owner)
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["max_users"] == 25
