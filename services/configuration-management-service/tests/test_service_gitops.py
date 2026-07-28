"""Tests for :class:`app.services.gitops.ConfigurationGitOpsService`."""

from __future__ import annotations

import base64
import uuid

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.dependency import DependencyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.gitops.credentials import GitCredentialResolver
from app.models.enums import GitProvider, GitSyncStatus
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository
from app.services.gitops import ConfigurationGitOpsService
from tests.conftest import SECRETS_SERVICE_BASE_URL, make_profile


def build_service(
    db_session: AsyncSession, http_client: httpx.AsyncClient
) -> ConfigurationGitOpsService:
    return ConfigurationGitOpsService(
        ConfigurationGitRepositoryRepository(db_session),
        http_client,
        GitCredentialResolver(http_client, base_url=SECRETS_SERVICE_BASE_URL),
    )


async def test_register_creates_repository(db_session: AsyncSession) -> None:
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        org_id = uuid.uuid4()

        repository = await service.register(
            organization_id=org_id,
            project_id=None,
            profile_id=None,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )

        assert repository.provider == GitProvider.GITHUB
        assert repository.sync_status == GitSyncStatus.PENDING


async def test_list_for_org(db_session: AsyncSession) -> None:
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        org_id = uuid.uuid4()
        await service.register(
            organization_id=org_id,
            project_id=None,
            profile_id=None,
            provider=GitProvider.GITEA,
            repository_url="https://gitea.internal/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )

        records = await service.list_for_org(org_id)
        assert len(records) == 1


async def test_sync_profile_public_repo_creates_file(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session, variables={"port": "80"})
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )

        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/webapp/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            status_code=404,
        )
        httpx_mock.add_response(
            method="PUT",
            url=f"https://api.github.com/repos/acme/webapp/contents/profiles/{profile.id}.json",
            json={"commit": {"sha": "abc123"}},
            status_code=201,
        )

        result = await service.sync_profile(
            repository.id, profile=profile, caller_token="", commit_message="sync"
        )

        assert result.created is True
        assert result.commit_sha == "abc123"

    updated = await service.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.SYNCED
    assert updated.last_synced_at is not None


async def test_sync_profile_resolves_credential_via_secrets_service(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session)
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/private-repo",
            branch="main",
            credential_ref="secret-123",
            webhook_secret_ref=None,
        )

        httpx_mock.add_response(
            method="GET",
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/secret-123",
            json={"data": {"value": "gh-token-xyz"}},
            status_code=200,
        )
        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/private-repo/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            status_code=404,
        )
        httpx_mock.add_response(
            method="PUT",
            url=(
                "https://api.github.com/repos/acme/private-repo/contents/"
                f"profiles/{profile.id}.json"
            ),
            json={"commit": {"sha": "def456"}},
            status_code=201,
        )

        await service.sync_profile(
            repository.id, profile=profile, caller_token="caller-jwt", commit_message="sync"
        )

    request = httpx_mock.get_requests(url=f"{SECRETS_SERVICE_BASE_URL}/secrets/secret-123")[0]
    assert request.headers["Authorization"] == "Bearer caller-jwt"


async def test_sync_profile_detects_conflict_when_already_synced(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session, variables={"port": "80"})
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )
        repository.sync_status = GitSyncStatus.SYNCED
        await db_session.flush()

        remote_content = base64.b64encode(b'{"variables": {"port": "9999"}}').decode("ascii")
        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/webapp/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            json={"content": remote_content, "sha": "old-sha"},
            status_code=200,
        )

        with pytest.raises(ConflictError):
            await service.sync_profile(
                repository.id, profile=profile, caller_token="", commit_message="sync"
            )

    updated = await service.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.CONFLICT


async def test_sync_profile_force_bypasses_conflict_check(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session, variables={"port": "80"})
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )
        repository.sync_status = GitSyncStatus.SYNCED
        await db_session.flush()

        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/webapp/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            json={"content": "eyJ4IjogMX0=", "sha": "old-sha"},
            status_code=200,
        )
        httpx_mock.add_response(
            method="PUT",
            url=f"https://api.github.com/repos/acme/webapp/contents/profiles/{profile.id}.json",
            json={"commit": {"sha": "forced-sha"}},
            status_code=200,
        )

        result = await service.sync_profile(
            repository.id,
            profile=profile,
            caller_token="",
            commit_message="sync",
            force=True,
        )
        assert result.commit_sha == "forced-sha"


async def test_sync_profile_maps_provider_error_to_dependency_error(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session)
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )

        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/webapp/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            status_code=404,
        )
        httpx_mock.add_response(
            method="PUT",
            url=f"https://api.github.com/repos/acme/webapp/contents/profiles/{profile.id}.json",
            status_code=500,
        )

        with pytest.raises(DependencyError):
            await service.sync_profile(
                repository.id, profile=profile, caller_token="", commit_message="sync"
            )

    updated = await service.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.ERROR


async def test_conflict_detection_survives_a_real_reload(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    """Regression: ``sync_status`` comes back from Postgres as a ``str``.

    ``GitSyncStatus`` is stored in a plain ``String`` column, so a row
    loaded from the database yields a raw ``str`` and an ``is``
    comparison against the enum is ``False`` for *every* stored
    repository. That silently disabled conflict detection entirely:
    ``sync_profile(force=False)`` overwrote the remote unconditionally,
    destroying whatever anyone else had committed, and ``force=True``
    meant nothing.

    ``test_sync_profile_detects_conflict_when_already_synced`` above
    does not catch it, because assigning the enum in Python leaves the
    identity-mapped object holding a real enum. The ``refresh`` here is
    what makes production behaviour visible.
    """
    profile = await make_profile(db_session, variables={"port": "80"})
    async with httpx.AsyncClient() as http_client:
        service = build_service(db_session, http_client)
        repository = await service.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/webapp",
            branch="main",
            credential_ref=None,
            webhook_secret_ref=None,
        )
        repository.sync_status = GitSyncStatus.SYNCED
        await db_session.flush()

        # Force a genuine re-SELECT, exactly as the next request would.
        await db_session.refresh(repository)
        assert not isinstance(repository.sync_status, GitSyncStatus), (
            "the column really does return a raw str; if this ever becomes "
            "a true enum, the normalisation can be dropped"
        )

        remote_content = base64.b64encode(b'{"variables": {"port": "9999"}}').decode("ascii")
        httpx_mock.add_response(
            method="GET",
            url=(
                "https://api.github.com/repos/acme/webapp/contents/"
                f"profiles/{profile.id}.json?ref=main"
            ),
            json={"content": remote_content, "sha": "old-sha"},
            status_code=200,
        )

        with pytest.raises(ConflictError):
            await service.sync_profile(
                repository.id, profile=profile, caller_token="", commit_message="sync"
            )

    updated = await service.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.CONFLICT
