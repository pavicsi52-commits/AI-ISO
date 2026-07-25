"""Tests for ``app/api/secret.py`` -- the full REST lifecycle, including
access-control enforcement.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SecretAccessAction
from app.models.secret_access import SecretAccessGrant
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_version import SecretVersionRepository


async def test_create_secret_makes_caller_owner(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "api-created-secret",
            "secret_type": "password",
            "owner_id": str(caller),
            "value": "s3cr3t",
        },
        headers=auth_headers(caller),
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["owner_id"] == str(caller)
    assert body["current_version"] == 1
    assert "value" not in body


async def test_create_secret_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "no-auth",
            "secret_type": "password",
            "owner_id": str(uuid.uuid4()),
            "value": "value",
        },
    )
    assert response.status_code == 401


async def test_create_secret_stores_ciphertext_in_database(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "db-check",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "never-in-plaintext",
        },
        headers=auth_headers(caller),
    )
    secret_id = uuid.UUID(response.json()["data"]["id"])

    version = await SecretVersionRepository(db_session).get_current(secret_id)
    assert version is not None
    assert version.ciphertext != "never-in-plaintext"
    assert "never-in-plaintext" not in version.ciphertext


async def test_owner_can_get_decrypted_secret(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "readable",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "read-me",
        },
        headers=auth_headers(caller),
    )
    secret_id = create_response.json()["data"]["id"]

    get_response = await client.get(f"/secrets/{secret_id}", headers=auth_headers(caller))
    assert get_response.status_code == 200
    assert get_response.json()["data"]["value"] == "read-me"


async def test_stranger_without_grant_is_denied(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    owner = uuid.uuid4()
    stranger = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "private-secret",
            "secret_type": "custom",
            "owner_id": str(owner),
            "value": "no-peeking",
        },
        headers=auth_headers(owner),
    )
    secret_id = create_response.json()["data"]["id"]

    denied_response = await client.get(f"/secrets/{secret_id}", headers=auth_headers(stranger))
    assert denied_response.status_code == 403


async def test_granted_principal_can_access(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    owner = uuid.uuid4()
    grantee = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "shared-secret",
            "secret_type": "custom",
            "owner_id": str(owner),
            "value": "shared-value",
        },
        headers=auth_headers(owner),
    )
    body = create_response.json()["data"]
    secret_id = uuid.UUID(body["id"])

    grant = SecretAccessGrant(
        secret_id=secret_id,
        organization_id=uuid.UUID(body["organization_id"]),
        principal_id=grantee,
        actions=[SecretAccessAction.READ.value],
        granted_by=owner,
    )
    db_session.add(grant)
    await db_session.flush()

    granted_response = await client.get(f"/secrets/{secret_id}", headers=auth_headers(grantee))
    assert granted_response.status_code == 200
    assert granted_response.json()["data"]["value"] == "shared-value"


async def test_update_secret_changes_metadata(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "updatable",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )
    secret_id = create_response.json()["data"]["id"]

    update_response = await client.put(
        f"/secrets/{secret_id}",
        json={"name": "updated-name", "status": "disabled"},
        headers=auth_headers(caller),
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["name"] == "updated-name"
    assert update_response.json()["data"]["status"] == "disabled"


async def test_rotate_secret_bumps_version(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "rotatable",
            "secret_type": "password",
            "owner_id": str(caller),
            "value": "old-value",
            "tags": ["prod"],
        },
        headers=auth_headers(caller),
    )
    secret_id = create_response.json()["data"]["id"]

    rotate_response = await client.post(
        f"/secrets/{secret_id}/rotate",
        json={"new_value": "new-value"},
        headers=auth_headers(caller),
    )
    assert rotate_response.status_code == 200
    assert rotate_response.json()["data"]["current_version"] == 2
    assert rotate_response.json()["data"]["tags"] == ["prod"]

    get_response = await client.get(f"/secrets/{secret_id}", headers=auth_headers(caller))
    assert get_response.json()["data"]["value"] == "new-value"


async def test_delete_secret(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "deletable",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )
    secret_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(f"/secrets/{secret_id}", headers=auth_headers(caller))
    assert delete_response.status_code == 200

    get_response = await client.get(f"/secrets/{secret_id}", headers=auth_headers(caller))
    assert get_response.status_code == 404


async def test_list_secrets_never_includes_value(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    await client.post(
        "/secrets",
        json={
            "organization_id": str(org_id),
            "name": "listed-secret",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "should-not-leak",
        },
        headers=auth_headers(caller),
    )

    list_response = await client.get(
        "/secrets", params={"organization_id": str(org_id)}, headers=auth_headers(caller)
    )
    assert list_response.status_code == 200
    for item in list_response.json()["data"]:
        assert "value" not in item


async def test_get_decrypted_records_audit_entry(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    caller = uuid.uuid4()
    create_response = await client.post(
        "/secrets",
        json={
            "organization_id": str(uuid.uuid4()),
            "name": "audited-via-api",
            "secret_type": "custom",
            "owner_id": str(caller),
            "value": "value",
        },
        headers=auth_headers(caller),
    )
    secret_id = uuid.UUID(create_response.json()["data"]["id"])

    await client.get(f"/secrets/{secret_id}", headers=auth_headers(caller))

    entries = await SecretAuditRepository(db_session).list_for_secret(secret_id)
    assert any(entry.action == "read" for entry in entries)


async def test_access_denied_when_secret_not_found(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.get(f"/secrets/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4()))
    assert response.status_code == 404
