"""GitOps repository registration and profile synchronization.

Per docs/039 "GITOPS" "Support": GitHub, GitLab, Azure DevOps,
Bitbucket, Gitea, Branch Tracking, Pull Requests, Commit History,
Webhook Integration, Synchronization, Conflict Detection.
:meth:`ConfigurationGitOpsService.sync_profile` fetches the remote
file's current content immediately before writing; if it already
exists, differs from what is about to be written, and the repository
was already marked ``SYNCED`` (meaning something changed the remote
file outside of this service since the last successful sync), the sync
is refused as a conflict unless the caller passes ``force=True``
("Conflict Detection").
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.dependency import DependencyError

from app.gitops.base import GitOpsError, GitSyncResult
from app.gitops.credentials import GitCredentialResolver
from app.gitops.factory import build_git_provider_client
from app.models.configuration_git_repository import ConfigurationGitRepository
from app.models.configuration_profile import ConfigurationProfile
from app.models.enums import GitProvider, GitSyncStatus
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository


def _sync_status_of(repository: ConfigurationGitRepository) -> GitSyncStatus:
    """Return a repository's sync status as a genuine :class:`GitSyncStatus`.

    ``sync_status`` is annotated ``Mapped[GitSyncStatus]`` but stored in
    a plain ``String`` column, so SQLAlchemy hands back a raw ``str``
    for any row loaded from Postgres. Comparing that with ``is`` was
    ``False`` for *every* stored repository, which silently disabled
    the conflict detection below: ``sync_profile(force=False)``
    overwrote the remote unconditionally, destroying whatever anyone
    else had committed, and ``force=True`` meant nothing. Normalising
    first makes the check mean what it reads as.
    """
    status = repository.sync_status
    return status if isinstance(status, GitSyncStatus) else GitSyncStatus(status)


class ConfigurationGitOpsService:
    """Registers Git repositories and synchronizes profile content to them."""

    def __init__(
        self,
        git_repositories: ConfigurationGitRepositoryRepository,
        http_client: httpx.AsyncClient,
        credentials: GitCredentialResolver,
    ) -> None:
        self._git_repositories = git_repositories
        self._http_client = http_client
        self._credentials = credentials

    async def get_by_id(self, repository_id: UUID) -> ConfigurationGitRepository:
        """Return the Git repository registration identified by *repository_id*.

        Raises:
            NotFoundError: If no such repository is registered.
        """
        return await self._git_repositories.require_by_id(repository_id)

    async def list_for_org(self, organization_id: UUID) -> list[ConfigurationGitRepository]:
        """Every Git repository registered for *organization_id*."""
        return await self._git_repositories.list_for_org(organization_id)

    async def register(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        profile_id: UUID | None,
        provider: GitProvider,
        repository_url: str,
        branch: str,
        credential_ref: str | None,
        webhook_secret_ref: str | None,
    ) -> ConfigurationGitRepository:
        """Register a Git repository to back a profile's GitOps workflow."""
        return await self._git_repositories.create(
            ConfigurationGitRepository(
                organization_id=organization_id,
                project_id=project_id,
                profile_id=profile_id,
                provider=provider,
                repository_url=repository_url,
                branch=branch,
                sync_status=GitSyncStatus.PENDING,
                credential_ref=credential_ref,
                webhook_secret_ref=webhook_secret_ref,
            )
        )

    async def sync_profile(
        self,
        repository_id: UUID,
        *,
        profile: ConfigurationProfile,
        caller_token: str,
        commit_message: str,
        force: bool = False,
    ) -> GitSyncResult:
        """Push *profile*'s current desired state to its registered Git
        repository ("Synchronization").

        Raises:
            ConflictError: If the remote file changed since the last
                successful sync and *force* is ``False`` ("Conflict Detection").
            DependencyError: If the Git provider request fails.
        """
        repository = await self.get_by_id(repository_id)
        token = ""
        if repository.credential_ref is not None:
            token = await self._credentials.resolve(
                repository.credential_ref, caller_token=caller_token
            )
        client = build_git_provider_client(repository, client=self._http_client, token=token)

        path = f"profiles/{profile.id}.json"
        content = json.dumps(
            {"variables": profile.variables, "target_assets": profile.target_assets},
            indent=2,
            sort_keys=True,
        )

        if not force and _sync_status_of(repository) is GitSyncStatus.SYNCED:
            try:
                remote_content = await client.get_file_content(path, ref=repository.branch)
            except GitOpsError as exc:
                raise DependencyError(str(exc)) from exc
            if remote_content is not None and remote_content != content:
                repository.sync_status = GitSyncStatus.CONFLICT
                await self._git_repositories.update(repository)
                raise ConflictError(
                    f"Remote file {path!r} on branch {repository.branch!r} changed since the "
                    "last sync; pass force=True to overwrite."
                )

        try:
            result = await client.sync_file(
                path, content, branch=repository.branch, message=commit_message
            )
        except GitOpsError as exc:
            repository.sync_status = GitSyncStatus.ERROR
            await self._git_repositories.update(repository)
            raise DependencyError(str(exc)) from exc

        repository.sync_status = GitSyncStatus.SYNCED
        repository.last_synced_at = datetime.now(UTC)
        await self._git_repositories.update(repository)
        return result


__all__ = ["ConfigurationGitOpsService"]
