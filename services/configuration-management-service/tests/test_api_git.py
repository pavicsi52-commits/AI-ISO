"""Tests for ``GET/POST /configurations/git``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import GitProvider
from tests.conftest import AuthHeadersFn


async def test_register_and_list_git_repositories(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    org_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations/git",
        json={
            "organization_id": str(org_id),
            "provider": GitProvider.GITHUB.value,
            "repository_url": "https://github.com/acme/webapp",
            "branch": "main",
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert create_response.status_code == 201
    assert create_response.json()["data"]["sync_status"] == "pending"

    list_response = await client.get(
        "/configurations/git",
        params={"organization_id": str(org_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1
    assert list_response.json()["data"][0]["provider"] == "github"
