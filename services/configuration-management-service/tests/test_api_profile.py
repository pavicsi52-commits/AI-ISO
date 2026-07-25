"""Tests for ``/configurations`` and its sub-resource endpoints."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupType, ConfigurationType, EnvironmentType, RestoreType
from tests.conftest import AuthHeadersFn, make_profile


async def test_create_and_get_profile(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    caller_id = uuid.uuid4()
    org_id = uuid.uuid4()
    response = await client.post(
        "/configurations",
        json={
            "organization_id": str(org_id),
            "profile_name": "web-tier",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
            "variables": {"port": "80"},
        },
        headers=auth_headers(caller_id),
    )
    assert response.status_code == 201
    profile_id = response.json()["data"]["id"]

    fetched = await client.get(f"/configurations/{profile_id}", headers=auth_headers(caller_id))
    assert fetched.status_code == 200
    assert fetched.json()["data"]["profile_name"] == "web-tier"


async def test_list_profiles_for_org(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    caller_id = uuid.uuid4()
    org_id = uuid.uuid4()
    await client.post(
        "/configurations",
        json={
            "organization_id": str(org_id),
            "profile_name": "profile-a",
            "environment": EnvironmentType.STAGING.value,
            "configuration_type": ConfigurationType.DATABASE.value,
        },
        headers=auth_headers(caller_id),
    )

    response = await client.get(
        "/configurations", params={"organization_id": str(org_id)}, headers=auth_headers(caller_id)
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_get_profile_not_found(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    response = await client.get(
        f"/configurations/{uuid.uuid4()}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_update_profile(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    caller_id = uuid.uuid4()
    profile = await make_profile(db_session)

    response = await client.put(
        f"/configurations/{profile.id}",
        json={
            "profile_name": "renamed",
            "status": "active",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
            "variables": {"a": "1"},
        },
        headers=auth_headers(caller_id),
    )
    assert response.status_code == 200
    assert response.json()["data"]["profile_name"] == "renamed"
    assert response.json()["data"]["status"] == "active"


async def test_patch_profile(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session, profile_name="original")

    response = await client.patch(
        f"/configurations/{profile.id}",
        json={"description": "patched description"},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert response.json()["data"]["description"] == "patched description"
    assert response.json()["data"]["profile_name"] == "original"


async def test_delete_profile(
    client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
) -> None:
    profile = await make_profile(db_session)

    response = await client.delete(
        f"/configurations/{profile.id}", headers=auth_headers(uuid.uuid4())
    )
    assert response.status_code == 200
    assert response.json()["data"]["success"] is True

    follow_up = await client.get(
        f"/configurations/{profile.id}", headers=auth_headers(uuid.uuid4())
    )
    assert follow_up.status_code == 404


async def test_list_profile_versions(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    caller_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations",
        json={
            "organization_id": str(uuid.uuid4()),
            "profile_name": "versioned",
            "environment": EnvironmentType.DEVELOPMENT.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
        },
        headers=auth_headers(caller_id),
    )
    profile_id = create_response.json()["data"]["id"]

    response = await client.get(
        f"/configurations/{profile_id}/versions", headers=auth_headers(caller_id)
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_backup_and_restore_profile(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    caller_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations",
        json={
            "organization_id": str(uuid.uuid4()),
            "profile_name": "backup-target",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
            "variables": {"a": "1"},
        },
        headers=auth_headers(caller_id),
    )
    profile_id = create_response.json()["data"]["id"]

    backup_response = await client.post(
        f"/configurations/{profile_id}/backup",
        json={"backup_type": BackupType.SNAPSHOT.value, "encrypted": False},
        headers=auth_headers(caller_id),
    )
    assert backup_response.status_code == 201
    backup_id = backup_response.json()["data"]["id"]

    restore_response = await client.post(
        f"/configurations/{profile_id}/restore",
        json={
            "backup_id": backup_id,
            "restore_type": RestoreType.PROFILE.value,
            "preview_only": True,
        },
        headers=auth_headers(caller_id),
    )
    assert restore_response.status_code == 201
    assert restore_response.json()["data"]["preview_only"] is True


async def test_rollback_profile(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    caller_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations",
        json={
            "organization_id": str(uuid.uuid4()),
            "profile_name": "rollback-target",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
        },
        headers=auth_headers(caller_id),
    )
    profile_id = create_response.json()["data"]["id"]
    versions_response = await client.get(
        f"/configurations/{profile_id}/versions", headers=auth_headers(caller_id)
    )
    version_id = versions_response.json()["data"][0]["id"]

    response = await client.post(
        f"/configurations/{profile_id}/rollback",
        json={"to_version_id": version_id, "rollback_type": "version"},
        headers=auth_headers(caller_id),
    )
    assert response.status_code == 201
    assert response.json()["data"]["status"] == "pending"
