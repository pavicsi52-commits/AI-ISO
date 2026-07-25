"""Dispatch a :class:`app.models.enums.GitProvider` plus a
:class:`app.models.configuration_git_repository.ConfigurationGitRepository`
row to the matching concrete :class:`app.gitops.base.GitProviderClient`.

Each provider's :attr:`ConfigurationGitRepository.repository_url` is
parsed into that provider's own addressing scheme (owner/repo,
project-id, organization/project/repo, or workspace/repo-slug); the
caller is responsible for resolving :attr:`credential_ref` through
``services/secrets-management-service`` into a real *token* before
calling this factory, since this module never touches secrets storage
itself.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.gitops.azure_devops_client import AzureDevOpsClient
from app.gitops.base import GitOpsError, GitProviderClient
from app.gitops.bitbucket_client import BitbucketClient
from app.gitops.gitea_client import GiteaClient
from app.gitops.github_client import GitHubClient
from app.gitops.gitlab_client import GitLabClient
from app.models.configuration_git_repository import ConfigurationGitRepository
from app.models.enums import GitProvider

_AZURE_DEVOPS_GIT_INFIX_PARTS = 4


def _split_path(repository_url: str, *, expected_min_parts: int) -> list[str]:
    parsed = urlparse(repository_url)
    parts = [part for part in parsed.path.strip("/").removesuffix(".git").split("/") if part]
    if len(parts) < expected_min_parts:
        raise GitOpsError(
            f"Repository URL {repository_url!r} does not contain the expected "
            f"{expected_min_parts} path segment(s)"
        )
    return parts


def build_git_provider_client(
    repository: ConfigurationGitRepository, *, client: httpx.AsyncClient, token: str
) -> GitProviderClient:
    """Build the concrete client matching *repository*'s own provider."""
    provider = GitProvider(repository.provider)

    if provider is GitProvider.GITHUB:
        owner, repo = _split_path(repository.repository_url, expected_min_parts=2)[:2]
        return GitHubClient(client, owner=owner, repo=repo, token=token)

    if provider is GitProvider.GITLAB:
        parsed = urlparse(repository.repository_url)
        project_id = parsed.path.strip("/").removesuffix(".git")
        if not project_id:
            raise GitOpsError(f"Repository URL {repository.repository_url!r} has no project path")
        return GitLabClient(client, project_id=project_id, token=token)

    if provider is GitProvider.AZURE_DEVOPS:
        parts = _split_path(repository.repository_url, expected_min_parts=3)
        organization, project = parts[0], parts[1]
        has_git_infix = len(parts) >= _AZURE_DEVOPS_GIT_INFIX_PARTS and parts[2] == "_git"
        repo = parts[3] if has_git_infix else parts[-1]
        return AzureDevOpsClient(
            client, organization=organization, project=project, repo=repo, token=token
        )

    if provider is GitProvider.BITBUCKET:
        workspace, repo_slug = _split_path(repository.repository_url, expected_min_parts=2)[:2]
        return BitbucketClient(client, workspace=workspace, repo_slug=repo_slug, token=token)

    if provider is GitProvider.GITEA:
        parsed = urlparse(repository.repository_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        owner, repo = _split_path(repository.repository_url, expected_min_parts=2)[:2]
        return GiteaClient(client, base_url=base_url, owner=owner, repo=repo, token=token)

    raise GitOpsError(f"Unsupported Git provider: {provider!r}")  # pragma: no cover


__all__ = ["build_git_provider_client"]
