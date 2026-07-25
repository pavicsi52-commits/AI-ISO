"""Tests for ``app/api/project_member.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import ADMINISTRATOR_ROLE_ID
from tests.conftest import add_member, make_project_with_owner


async def test_list_members_requires_membership(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    forbidden = await client.get(f"/projects/{project.id}/members", headers=auth_headers(outsider))
    assert forbidden.status_code == 403

    allowed = await client.get(f"/projects/{project.id}/members", headers=auth_headers(owner))
    assert allowed.status_code == 200
    assert len(allowed.json()["data"]) == 1


async def test_add_member_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    new_member = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    forbidden = await client.post(
        f"/projects/{project.id}/members",
        json={"user_id": str(new_member), "role_code": "developer"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.post(
        f"/projects/{project.id}/members",
        json={"user_id": str(new_member), "role_code": "developer"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 201
    body = allowed.json()["data"]
    assert body["role_code"] == "developer"
    assert body["user_id"] == str(new_member)


async def test_remove_member_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    member = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)
    await add_member(
        db_session, project.id, project.organization_id, member, role_id=ADMINISTRATOR_ROLE_ID
    )

    forbidden = await client.delete(
        f"/projects/{project.id}/members/{member}", headers=auth_headers(uuid.uuid4())
    )
    assert forbidden.status_code == 403

    allowed = await client.delete(
        f"/projects/{project.id}/members/{member}", headers=auth_headers(owner)
    )
    assert allowed.status_code == 200

    listing = await client.get(f"/projects/{project.id}/members", headers=auth_headers(owner))
    user_ids = {m["user_id"] for m in listing.json()["data"]}
    assert str(member) not in user_ids


async def test_update_member_role(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    member = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)
    await add_member(
        db_session, project.id, project.organization_id, member, role_id=ADMINISTRATOR_ROLE_ID
    )

    response = await client.put(
        f"/projects/{project.id}/members/{member}/roles",
        json={"role_code": "viewer"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["role_code"] == "viewer"


async def test_update_member_role_to_owner_transfers_ownership(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    member = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)
    await add_member(
        db_session, project.id, project.organization_id, member, role_id=ADMINISTRATOR_ROLE_ID
    )

    response = await client.put(
        f"/projects/{project.id}/members/{member}/roles",
        json={"role_code": "owner"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["data"]["role_code"] == "owner"

    project_response = await client.get(f"/projects/{project.id}", headers=auth_headers(owner))
    assert project_response.json()["data"]["owner_id"] == str(member)

    listing = await client.get(f"/projects/{project.id}/members", headers=auth_headers(owner))
    roles_by_user = {m["user_id"]: m["role_code"] for m in listing.json()["data"]}
    assert roles_by_user[str(owner)] == "administrator"
    assert roles_by_user[str(member)] == "owner"
