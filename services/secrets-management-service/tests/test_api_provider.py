"""Tests for ``app/api/provider.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_create_provider_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/providers",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "no-auth",
            "provider_type": "internal_vault",
        },
    )
    assert response.status_code == 401


async def test_create_and_list_provider(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()

    create_response = await client.post(
        "/providers",
        json={
            "organization_id": str(org_id),
            "name": "hashicorp-vault",
            "provider_type": "hashicorp_vault",
        },
        headers=auth_headers(caller),
    )
    assert create_response.status_code == 201
    assert create_response.json()["data"]["provider_type"] == "hashicorp_vault"

    list_response = await client.get(
        "/providers", params={"organization_id": str(org_id)}, headers=auth_headers(caller)
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1


async def test_create_duplicate_provider_conflicts(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    payload = {
        "organization_id": str(org_id),
        "name": "duplicate-name",
        "provider_type": "aws_secrets_manager",
    }
    first = await client.post("/providers", json=payload, headers=auth_headers(caller))
    assert first.status_code == 201

    second = await client.post("/providers", json=payload, headers=auth_headers(caller))
    assert second.status_code == 409
