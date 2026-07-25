"""Tests for ``app/api/project.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectVisibility
from tests.conftest import make_project, make_project_with_owner

_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


async def test_create_project_makes_caller_owner(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/projects",
        json={
            "organization_id": str(_ORG_ID),
            "name": "Acme Plant",
            "code": f"acme-{caller.hex[:8]}",
        },
        headers=auth_headers(caller),
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["name"] == "Acme Plant"
    assert body["status"] == "draft"
    assert body["owner_id"] == str(caller)

    project_id = body["id"]
    get_response = await client.get(f"/projects/{project_id}", headers=auth_headers(caller))
    assert get_response.status_code == 200


async def test_create_project_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/projects", json={"organization_id": str(_ORG_ID), "name": "No Auth", "code": "no-auth"}
    )
    assert response.status_code == 401


async def test_create_project_duplicate_code_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    headers = auth_headers(caller)
    payload = {"organization_id": str(_ORG_ID), "name": "First", "code": f"dup-{caller.hex[:8]}"}
    first = await client.post("/projects", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post(
        "/projects",
        json={"organization_id": str(_ORG_ID), "name": "Second", "code": payload["code"]},
        headers=headers,
    )
    assert second.status_code == 409


async def test_list_projects_hides_private_from_non_members(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    org_id = uuid.uuid4()
    private = await make_project_with_owner(
        db_session, owner, organization_id=org_id, visibility=ProjectVisibility.PRIVATE
    )
    public = await make_project(
        db_session, organization_id=org_id, owner_id=owner, visibility=ProjectVisibility.PUBLIC
    )

    as_outsider = await client.get(
        f"/projects?organization_id={org_id}", headers=auth_headers(outsider)
    )
    outsider_ids = {p["id"] for p in as_outsider.json()["data"]}
    assert str(private.id) not in outsider_ids
    assert str(public.id) in outsider_ids

    as_owner = await client.get(f"/projects?organization_id={org_id}", headers=auth_headers(owner))
    owner_ids = {p["id"] for p in as_owner.json()["data"]}
    assert str(private.id) in owner_ids
    assert str(public.id) in owner_ids


async def test_get_project_private_denies_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner, visibility=ProjectVisibility.PRIVATE)

    response = await client.get(f"/projects/{project.id}", headers=auth_headers(outsider))
    assert response.status_code == 403


async def test_get_project_public_allows_non_member(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner, visibility=ProjectVisibility.PUBLIC)

    response = await client.get(f"/projects/{project.id}", headers=auth_headers(outsider))
    assert response.status_code == 200


async def test_get_project_not_found(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(f"/projects/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 404


async def test_update_project_requires_admin(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    forbidden = await client.put(
        f"/projects/{project.id}",
        json={"name": "Renamed", "status": "active"},
        headers=auth_headers(outsider),
    )
    assert forbidden.status_code == 403

    allowed = await client.put(
        f"/projects/{project.id}",
        json={"name": "Renamed", "status": "active"},
        headers=auth_headers(owner),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["name"] == "Renamed"


async def test_patch_project_partial_update(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner, name="Original")

    response = await client.patch(
        f"/projects/{project.id}", json={"category": "manufacturing"}, headers=auth_headers(owner)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["category"] == "manufacturing"
    assert body["name"] == "Original"


async def test_delete_project_requires_admin_then_soft_deletes(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    forbidden = await client.delete(f"/projects/{project.id}", headers=auth_headers(outsider))
    assert forbidden.status_code == 403

    allowed = await client.delete(f"/projects/{project.id}", headers=auth_headers(owner))
    assert allowed.status_code == 200

    after = await client.get(f"/projects/{project.id}", headers=auth_headers(owner))
    assert after.status_code == 404


async def test_clone_project_creates_new_owner_membership(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner, code="source-code")

    response = await client.post(
        f"/projects/{project.id}/clone",
        json={"name": "Cloned", "code": "cloned-code"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201
    clone_id = response.json()["data"]["id"]

    members_response = await client.get(
        f"/projects/{clone_id}/members", headers=auth_headers(owner)
    )
    roles = {m["role_code"] for m in members_response.json()["data"]}
    assert "owner" in roles


async def test_archive_and_restore_project(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    archived = await client.post(
        f"/projects/{project.id}/archive",
        json={"reason": "quarter end"},
        headers=auth_headers(owner),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"
    assert archived.json()["data"]["archived_at"] is not None

    restored = await client.post(f"/projects/{project.id}/restore", headers=auth_headers(owner))
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "active"
    assert restored.json()["data"]["archived_at"] is None


async def test_restore_without_archive_not_found(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    project = await make_project_with_owner(db_session, owner)

    response = await client.post(f"/projects/{project.id}/restore", headers=auth_headers(owner))
    assert response.status_code == 404
