"""Common contract every Git provider client implements.

Per docs/039 "GITOPS" "Support": GitHub, GitLab, Azure DevOps,
Bitbucket, Gitea, Branch Tracking, Pull Requests, Commit History,
Webhook Integration, Synchronization, Conflict Detection. Each
provider's own REST contract is genuinely different (GitHub/Gitea's
content API is base64-blob-plus-SHA; GitLab's is project-id-plus
URL-encoded path; Azure DevOps pushes a full git ref update; Bitbucket
uses its own v2.0 source API) -- this module only fixes the *shape*
every provider client returns, not a shared implementation, matching
the same "lean, hand-built REST client per provider, real documented
contract, no heavy SDK" precedent
``services/discovery-service``'s own Azure/GCP/Oracle/IBM cloud
providers established. "Webhook Integration" (receiving push events)
and "Conflict Detection" (comparing local vs. remote content before a
sync) are service-layer concerns built on top of these primitives, not
client operations of their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GitOpsError(Exception):
    """A Git provider request failed or was misconfigured."""


@dataclass(frozen=True, slots=True)
class GitBranch:
    """One branch, per "Branch Tracking"."""

    name: str
    commit_sha: str


@dataclass(frozen=True, slots=True)
class GitCommit:
    """One commit, per "Commit History"."""

    sha: str
    message: str
    author: str


@dataclass(frozen=True, slots=True)
class GitSyncResult:
    """The outcome of writing one file, per "Synchronization"."""

    commit_sha: str
    created: bool


@dataclass(frozen=True, slots=True)
class GitPullRequest:
    """One pull/merge request, per "Pull Requests"."""

    number: int
    url: str
    state: str


class GitProviderClient(Protocol):
    """The operations every Git provider client implements."""

    async def get_default_branch(self) -> str:
        """Return the repository's default branch name."""
        ...

    async def list_branches(self) -> list[GitBranch]:
        """List every branch ("Branch Tracking")."""
        ...

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        """List the most recent commits on *branch* ("Commit History")."""
        ...

    async def get_file_content(self, path: str, *, ref: str) -> str | None:
        """Return the text content of *path* at *ref*, or ``None`` if absent."""
        ...

    async def sync_file(
        self, path: str, content: str, *, branch: str, message: str
    ) -> GitSyncResult:
        """Create or update *path* on *branch* ("Synchronization")."""
        ...

    async def create_pull_request(
        self, *, title: str, head_branch: str, base_branch: str, body: str
    ) -> GitPullRequest:
        """Open a pull/merge request from *head_branch* into *base_branch*
        ("Pull Requests").
        """
        ...


__all__ = [
    "GitBranch",
    "GitCommit",
    "GitOpsError",
    "GitProviderClient",
    "GitPullRequest",
    "GitSyncResult",
]
