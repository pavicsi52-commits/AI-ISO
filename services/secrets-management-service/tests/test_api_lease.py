"""Tests for ``app/api/lease.py`` -- ``DELETE /leases/{id}``."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def _create_secret_and_lease(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]], owner: uuid.UUID
) -> tuple[str, str]:
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "leasable",
            "secret_type": "password",
            "owner_id": str(owner),
            "value": "leased-value",
        },
        headers=auth_headers(owner),
    )
    secret_id = create_response.json()["data"]["id"]

    lease_response = await client.post(
        f"/secrets/{secret_id}/lease",
        json={"principal_id": str(owner), "duration_seconds": 3600},
        headers=auth_headers(owner),
    )
    lease_id = lease_response.json()["data"]["id"]
    return secret_id, lease_id


async def test_revoke_lease_requires_auth(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    owner = uuid.uuid4()
    _secret_id, lease_id = await _create_secret_and_lease(client, auth_headers, owner)

    response = await client.delete(f"/leases/{lease_id}")
    assert response.status_code == 401


async def test_owner_can_revoke_lease(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    owner = uuid.uuid4()
    _secret_id, lease_id = await _create_secret_and_lease(client, auth_headers, owner)

    response = await client.delete(f"/leases/{lease_id}", headers=auth_headers(owner))
    assert response.status_code == 200


async def test_stranger_cannot_revoke_lease(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    owner = uuid.uuid4()
    stranger = uuid.uuid4()
    _secret_id, lease_id = await _create_secret_and_lease(client, auth_headers, owner)

    response = await client.delete(f"/leases/{lease_id}", headers=auth_headers(stranger))
    assert response.status_code == 403


async def test_revoke_missing_lease_returns_404(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.delete(f"/leases/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 404
