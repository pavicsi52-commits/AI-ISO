"""Tests for ``app/api/organization_branding.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner


async def test_get_branding_creates_defaults_for_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/branding", headers=auth_headers(owner)
    )
    assert response.status_code == 200
    assert response.json()["data"]["theme"] == "light"


async def test_get_branding_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/branding", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


async def test_update_branding_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/organizations/{organization.id}/branding",
        json={"primary_color": "#000000"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/organizations/{organization.id}/branding",
        json={"primary_color": "#FF0000", "theme": "dark"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["primary_color"] == "#FF0000"
    assert allowed.json()["data"]["theme"] == "dark"
