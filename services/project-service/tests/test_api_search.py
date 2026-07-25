"""Tests for ``app/api/search.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectStatus, ProjectVisibility
from tests.conftest import make_project, make_project_with_owner


async def test_search_by_query_and_organization(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    await make_project(
        db_session,
        organization_id=org_id,
        name="Refinery Alpha",
        visibility=ProjectVisibility.PUBLIC,
    )
    await make_project(
        db_session,
        organization_id=org_id,
        name="Pipeline Beta",
        visibility=ProjectVisibility.PUBLIC,
    )
    await make_project(
        db_session, organization_id=uuid.uuid4(), name="Refinery Other Org"
    )  # different org, must not appear

    response = await client.get(
        f"/projects/search?organization_id={org_id}&q=Refinery", headers=auth_headers(caller)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    names = {p["name"] for p in body["items"]}
    assert names == {"Refinery Alpha"}
    assert body["pagination"]["total"] == 1


async def test_search_hides_private_projects_from_non_members(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    outsider = uuid.uuid4()
    org_id = uuid.uuid4()
    await make_project_with_owner(
        db_session,
        owner,
        organization_id=org_id,
        name="Secret Project",
        visibility=ProjectVisibility.PRIVATE,
    )

    response = await client.get(
        f"/projects/search?organization_id={org_id}", headers=auth_headers(outsider)
    )
    assert response.json()["data"]["items"] == []

    as_owner = await client.get(
        f"/projects/search?organization_id={org_id}", headers=auth_headers(owner)
    )
    assert len(as_owner.json()["data"]["items"]) == 1


async def test_search_filters_by_status(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    await make_project(
        db_session,
        organization_id=org_id,
        name="Active One",
        status=ProjectStatus.ACTIVE,
        visibility=ProjectVisibility.PUBLIC,
    )
    await make_project(
        db_session,
        organization_id=org_id,
        name="Draft One",
        status=ProjectStatus.DRAFT,
        visibility=ProjectVisibility.PUBLIC,
    )

    response = await client.get(
        f"/projects/search?organization_id={org_id}&status=draft", headers=auth_headers(caller)
    )
    names = {p["name"] for p in response.json()["data"]["items"]}
    assert names == {"Draft One"}


async def test_search_pagination(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    for i in range(3):
        await make_project(
            db_session,
            organization_id=org_id,
            name=f"Paged {i}",
            visibility=ProjectVisibility.PUBLIC,
        )

    response = await client.get(
        f"/projects/search?organization_id={org_id}&page=1&page_size=2",
        headers=auth_headers(caller),
    )
    body = response.json()["data"]
    assert len(body["items"]) == 2
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["has_next"] is True
