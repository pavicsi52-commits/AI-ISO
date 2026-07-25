"""Tests for :func:`app.gitops.factory.build_git_provider_client`."""

from __future__ import annotations

import httpx
import pytest

from app.gitops.azure_devops_client import AzureDevOpsClient
from app.gitops.base import GitOpsError
from app.gitops.bitbucket_client import BitbucketClient
from app.gitops.factory import build_git_provider_client
from app.gitops.gitea_client import GiteaClient
from app.gitops.github_client import GitHubClient
from app.gitops.gitlab_client import GitLabClient
from app.models.configuration_git_repository import ConfigurationGitRepository
from app.models.enums import GitProvider


def _repository(provider: GitProvider, repository_url: str) -> ConfigurationGitRepository:
    return ConfigurationGitRepository(provider=provider, repository_url=repository_url)


async def test_builds_github_client() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(GitProvider.GITHUB, "https://github.com/acme/webapp"),
            client=client,
            token="tok",
        )
        assert isinstance(result, GitHubClient)


async def test_builds_gitlab_client() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(GitProvider.GITLAB, "https://gitlab.com/acme/group/webapp"),
            client=client,
            token="tok",
        )
        assert isinstance(result, GitLabClient)


async def test_builds_azure_devops_client() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(
                GitProvider.AZURE_DEVOPS,
                "https://dev.azure.com/acme-org/acme-project/_git/webapp",
            ),
            client=client,
            token="tok",
        )
        assert isinstance(result, AzureDevOpsClient)


async def test_builds_bitbucket_client() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(GitProvider.BITBUCKET, "https://bitbucket.org/acme/webapp"),
            client=client,
            token="tok",
        )
        assert isinstance(result, BitbucketClient)


async def test_builds_gitea_client() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(GitProvider.GITEA, "https://gitea.internal/acme/webapp"),
            client=client,
            token="tok",
        )
        assert isinstance(result, GiteaClient)


async def test_github_url_too_short_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(GitOpsError):
            build_git_provider_client(
                _repository(GitProvider.GITHUB, "https://github.com/acme"),
                client=client,
                token="tok",
            )


async def test_gitlab_url_empty_path_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(GitOpsError):
            build_git_provider_client(
                _repository(GitProvider.GITLAB, "https://gitlab.com/"),
                client=client,
                token="tok",
            )


async def test_azure_devops_url_too_short_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(GitOpsError):
            build_git_provider_client(
                _repository(GitProvider.AZURE_DEVOPS, "https://dev.azure.com/acme-org"),
                client=client,
                token="tok",
            )


async def test_azure_devops_url_without_git_segment_uses_last_part() -> None:
    async with httpx.AsyncClient() as client:
        result = build_git_provider_client(
            _repository(
                GitProvider.AZURE_DEVOPS, "https://dev.azure.com/acme-org/acme-project/webapp"
            ),
            client=client,
            token="tok",
        )
        assert isinstance(result, AzureDevOpsClient)


async def test_bitbucket_url_too_short_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(GitOpsError):
            build_git_provider_client(
                _repository(GitProvider.BITBUCKET, "https://bitbucket.org/acme"),
                client=client,
                token="tok",
            )


async def test_gitea_url_too_short_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(GitOpsError):
            build_git_provider_client(
                _repository(GitProvider.GITEA, "https://gitea.internal/acme"),
                client=client,
                token="tok",
            )
