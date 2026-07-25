"""Tests for ``app/api/project_settings.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_project_with_owner


async def test_get_settings_creates_defaults_for_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    response = await client.get(f"/projects/{project.id}/settings", headers=auth_headers(owner))
    assert response.status_code == 200
    assert response.json()["data"]["default_environment"] is None


async def test_get_settings_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    response = await client.get(f"/projects/{project.id}/settings", headers=auth_headers(outsider))
    assert response.status_code == 403


async def test_update_settings_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/projects/{project.id}/settings",
        json={"default_environment": "staging"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/projects/{project.id}/settings",
        json={"default_environment": "production"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["default_environment"] == "production"
