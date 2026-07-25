"""Tests for ``app/api/organization_settings.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner


async def test_get_settings_creates_defaults_for_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/settings", headers=auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["default_language"] == "en"
    assert body["mfa_enforced"] is False


async def test_get_settings_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/settings", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


async def test_update_settings_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/organizations/{organization.id}/settings",
        json={"default_language": "fr", "mfa_enforced": True},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/organizations/{organization.id}/settings",
        json={"default_language": "fr", "mfa_enforced": True},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["default_language"] == "fr"
    assert allowed.json()["data"]["mfa_enforced"] is True


async def test_get_settings_not_found_for_unknown_org(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(
        f"/organizations/{uuid.uuid4()}/settings", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 403
