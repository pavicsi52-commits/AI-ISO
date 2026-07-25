"""Tests for ``app/api/ssh_key.py``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_create_ssh_key_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/ssh-keys",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "no-auth",
            "key_type": "ed25519",
            "owner_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401


async def test_create_and_list_ssh_key(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()

    create_response = await client.post(
        "/ssh-keys",
        json={
            "organization_id": str(org_id),
            "name": "deploy-key",
            "key_type": "ed25519",
            "owner_id": str(caller),
        },
        headers=auth_headers(caller),
    )
    assert create_response.status_code == 201
    body = create_response.json()["data"]
    assert body["public_key"].startswith("ssh-ed25519")
    assert body["private_key"].startswith("-----BEGIN PRIVATE KEY-----")

    list_response = await client.get(
        "/ssh-keys", params={"organization_id": str(org_id)}, headers=auth_headers(caller)
    )
    assert list_response.status_code == 200
    for item in list_response.json()["data"]:
        assert "private_key" not in item


async def test_create_ssh_key_mismatched_import_fields_rejected(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/ssh-keys",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "mismatched",
            "key_type": "rsa",
            "owner_id": str(caller),
            "public_key": "ssh-rsa AAAA...",
        },
        headers=auth_headers(caller),
    )
    assert response.status_code == 400


async def test_delete_ssh_key(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/ssh-keys",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "deletable",
            "key_type": "ed25519",
            "owner_id": str(caller),
        },
        headers=auth_headers(caller),
    )
    ssh_key_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(f"/ssh-keys/{ssh_key_id}", headers=auth_headers(caller))
    assert delete_response.status_code == 200
