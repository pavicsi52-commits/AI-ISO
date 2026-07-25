"""Tests for ``app/api/project_template.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_create_and_list_templates(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()

    create = await client.post(
        "/projects/templates",
        json={
            "organization_id": str(org_id),
            "name": "Industrial Standard",
            "category": "industrial",
        },
        headers=auth_headers(caller),
    )
    assert create.status_code == 201
    template_id = create.json()["data"]["id"]

    listing = await client.get(
        f"/projects/templates?organization_id={org_id}", headers=auth_headers(caller)
    )
    assert listing.status_code == 200
    assert [t["id"] for t in listing.json()["data"]] == [template_id]


async def test_create_template_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/projects/templates", json={"organization_id": str(uuid.uuid4()), "name": "No Auth"}
    )
    assert response.status_code == 401


async def test_create_duplicate_template_version_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    payload = {
        "organization_id": str(org_id),
        "name": "Cloud Standard",
        "template_version": "1.0.0",
    }

    first = await client.post("/projects/templates", json=payload, headers=auth_headers(caller))
    assert first.status_code == 201

    second = await client.post("/projects/templates", json=payload, headers=auth_headers(caller))
    assert second.status_code == 409
