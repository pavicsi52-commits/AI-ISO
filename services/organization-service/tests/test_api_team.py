"""Tests for ``app/api/team.py`` (both ``org_router`` and ``router``)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org_with_owner


async def test_create_and_list_teams(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    create = await client.post(
        f"/organizations/{organization.id}/teams",
        json={"name": "Platform", "code": "PLAT"},
        headers=auth_headers(owner),
    )
    assert create.status_code == 201
    team_id = create.json()["data"]["id"]

    listing = await client.get(
        f"/organizations/{organization.id}/teams", headers=auth_headers(owner)
    )
    assert listing.status_code == 200
    assert [t["id"] for t in listing.json()["data"]] == [team_id]


async def test_create_team_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.post(
        f"/organizations/{organization.id}/teams",
        json={"name": "Growth", "code": "GRW"},
        headers=auth_headers(outsider),
    )
    assert response.status_code == 403


async def test_list_teams_requires_membership(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)

    response = await client.get(
        f"/organizations/{organization.id}/teams", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


async def test_update_team_via_literal_path_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    create = await client.post(
        f"/organizations/{organization.id}/teams",
        json={"name": "Platform", "code": "PLAT"},
        headers=auth_headers(owner),
    )
    team_id = create.json()["data"]["id"]

    forbidden = await client.put(
        f"/teams/{team_id}", json={"name": "Renamed"}, headers=auth_headers(outsider)
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/teams/{team_id}", json={"name": "Renamed"}, headers=auth_headers(owner)
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["name"] == "Renamed"


async def test_delete_team_via_literal_path(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    organization = await make_org_with_owner(db_session, owner)
    create = await client.post(
        f"/organizations/{organization.id}/teams",
        json={"name": "Platform", "code": "PLAT"},
        headers=auth_headers(owner),
    )
    team_id = create.json()["data"]["id"]

    response = await client.delete(f"/teams/{team_id}", headers=auth_headers(owner))
    assert response.status_code == 200

    listing = await client.get(
        f"/organizations/{organization.id}/teams", headers=auth_headers(owner)
    )
    assert listing.json()["data"] == []
