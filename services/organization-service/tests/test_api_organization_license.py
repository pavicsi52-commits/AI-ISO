"""Tests for ``app/api/organization_license.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner


async def test_get_license_creates_pending_default(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/licenses", headers=auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "pending_activation"
    assert body["seat_count"] == 1


async def test_get_license_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/licenses", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


async def test_update_license_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    payload = {"license_type": "enterprise", "license_key": "ENT-12345", "seat_count": 50}

    forbidden = await client.put(
        f"/organizations/{organization.id}/licenses", json=payload, headers=auth_headers(outsider)
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/organizations/{organization.id}/licenses", json=payload, headers=auth_headers(owner)
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["license_type"] == "enterprise"
    assert allowed.json()["data"]["seat_count"] == 50
