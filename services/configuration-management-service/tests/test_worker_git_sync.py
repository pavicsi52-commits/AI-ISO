"""Tests for :func:`app.workers.git_sync_worker.build_git_sync_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.database import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.gitops.credentials import GitCredentialResolver
from app.models.enums import GitProvider, GitSyncStatus
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository
from app.services.gitops import ConfigurationGitOpsService
from app.services.profile import ConfigurationProfileService
from app.workers.git_sync_worker import GitSyncServices, build_git_sync_worker
from tests.conftest import SECRETS_SERVICE_BASE_URL, build_profile_service, make_profile


@asynccontextmanager
async def _factory(
    db_session: AsyncSession, http_client: httpx.AsyncClient
) -> AsyncIterator[GitSyncServices]:
    gitops = ConfigurationGitOpsService(
        ConfigurationGitRepositoryRepository(db_session),
        http_client,
        GitCredentialResolver(http_client, base_url=SECRETS_SERVICE_BASE_URL),
    )
    profiles: ConfigurationProfileService = build_profile_service(db_session)
    yield gitops, profiles


async def test_git_sync_worker_syncs_public_repository(
    db_session: AsyncSession, httpx_mock: HTTPXMock
) -> None:
    profile = await make_profile(db_session, variables={"port": "80"})
    async with httpx.AsyncClient() as http_client:
        gitops = ConfigurationGitOpsService(
            ConfigurationGitRepositoryRepository(db_session),
            http_client,
            GitCredentialResolver(http_client, base_url=SECRETS_SERVICE_BASE_URL),
        )
        repository = await gitops.register(
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

        handler = build_git_sync_worker(lambda: _factory(db_session, http_client))
        await handler({"repository_id": str(repository.id), "profile_id": str(profile.id)})

    updated = await gitops.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.SYNCED


async def test_git_sync_worker_skips_when_credential_needed_but_no_caller_token(
    db_session: AsyncSession,
) -> None:
    profile = await make_profile(db_session)
    async with httpx.AsyncClient() as http_client:
        gitops = ConfigurationGitOpsService(
            ConfigurationGitRepositoryRepository(db_session),
            http_client,
            GitCredentialResolver(http_client, base_url=SECRETS_SERVICE_BASE_URL),
        )
        repository = await gitops.register(
            organization_id=profile.organization_id,
            project_id=None,
            profile_id=profile.id,
            provider=GitProvider.GITHUB,
            repository_url="https://github.com/acme/private-repo",
            branch="main",
            credential_ref="secret-123",
            webhook_secret_ref=None,
        )

        handler = build_git_sync_worker(lambda: _factory(db_session, http_client))
        await handler({"repository_id": str(repository.id), "profile_id": str(profile.id)})

    updated = await gitops.get_by_id(repository.id)
    assert updated.sync_status == GitSyncStatus.PENDING


async def test_git_sync_worker_reraises_on_failure(db_session: AsyncSession) -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[GitSyncServices]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_git_sync_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"repository_id": str(uuid.uuid4()), "profile_id": str(uuid.uuid4())})
