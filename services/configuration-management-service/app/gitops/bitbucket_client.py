"""Bitbucket Cloud, via direct REST API 2.0 calls (``httpx``), against
the real documented contract -- no SDK dependency. Bitbucket's source
endpoint returns raw file bytes directly (no base64-JSON envelope like
GitHub/Gitea/GitLab), and writes are a ``multipart/form-data`` POST
where each changed file is its own form field, rather than a JSON body.
"""

from __future__ import annotations

import httpx

from app.gitops.base import GitBranch, GitCommit, GitOpsError, GitPullRequest, GitSyncResult

_API_BASE = "https://api.bitbucket.org/2.0"


class BitbucketClient:
    """A thin, real REST client for one Bitbucket Cloud repository."""

    def __init__(
        self, client: httpx.AsyncClient, *, workspace: str, repo_slug: str, token: str
    ) -> None:
        self._client = client
        self._workspace = workspace
        self._repo_slug = repo_slug
        self._headers = {"Authorization": f"Bearer {token}"}

    def _url(self, path: str) -> str:
        return f"{_API_BASE}/repositories/{self._workspace}/{self._repo_slug}{path}"

    async def _get(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(self._url(path), headers=self._headers, params=params)
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Bitbucket request to {path!r} failed: {exc}") from exc

    async def get_default_branch(self) -> str:
        response = await self._get("")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Bitbucket repository lookup failed: HTTP {response.status_code}")
        return str(response.json()["mainbranch"]["name"])

    async def list_branches(self) -> list[GitBranch]:
        response = await self._get("/refs/branches")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Bitbucket branch listing failed: HTTP {response.status_code}")
        return [
            GitBranch(name=item["name"], commit_sha=item["target"]["hash"])
            for item in response.json()["values"]
        ]

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        response = await self._get(f"/commits/{branch}", params={"pagelen": limit})
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Bitbucket commit listing failed: HTTP {response.status_code}")
        return [
            GitCommit(
                sha=item["hash"],
                message=item["message"],
                author=item["author"]["raw"],
            )
            for item in response.json()["values"]
        ]

    async def get_file_content(self, path: str, *, ref: str) -> str | None:
        response = await self._get(f"/src/{ref}/{path}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Bitbucket file lookup failed: HTTP {response.status_code}")
        return response.text

    async def sync_file(
        self, path: str, content: str, *, branch: str, message: str
    ) -> GitSyncResult:
        existing = await self._get(f"/src/{branch}/{path}")
        created = existing.status_code == httpx.codes.NOT_FOUND
        if not created and existing.status_code != httpx.codes.OK:
            raise GitOpsError(f"Bitbucket file lookup failed: HTTP {existing.status_code}")

        try:
            response = await self._client.post(
                self._url("/src"),
                headers=self._headers,
                data={"branch": branch, "message": message},
                files={path: content.encode("utf-8")},
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Bitbucket file sync failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(f"Bitbucket file sync failed: HTTP {response.status_code}")

        commits = await self.list_commits(branch, limit=1)
        commit_sha = commits[0].sha if commits else ""
        return GitSyncResult(commit_sha=commit_sha, created=created)

    async def create_pull_request(
        self, *, title: str, head_branch: str, base_branch: str, body: str
    ) -> GitPullRequest:
        try:
            response = await self._client.post(
                self._url("/pullrequests"),
                headers=self._headers,
                json={
                    "title": title,
                    "source": {"branch": {"name": head_branch}},
                    "destination": {"branch": {"name": base_branch}},
                    "description": body,
                },
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Bitbucket pull request creation failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(
                f"Bitbucket pull request creation failed: HTTP {response.status_code}"
            )
        payload = response.json()
        return GitPullRequest(
            number=payload["id"], url=payload["links"]["html"]["href"], state=payload["state"]
        )


__all__ = ["BitbucketClient"]
