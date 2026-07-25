"""GitHub, via direct REST API v3 calls (``httpx``), against the real
documented contract -- no ``PyGithub``/octokit dependency. Requires a
personal access token (or GitHub App installation token) resolved
through ``services/secrets-management-service`` before construction;
this client itself never resolves credentials.
"""

from __future__ import annotations

import base64

import httpx

from app.gitops.base import GitBranch, GitCommit, GitOpsError, GitPullRequest, GitSyncResult

_API_BASE = "https://api.github.com"


class GitHubClient:
    """A thin, real REST client for one GitHub repository."""

    def __init__(self, client: httpx.AsyncClient, *, owner: str, repo: str, token: str) -> None:
        self._client = client
        self._owner = owner
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _url(self, path: str) -> str:
        return f"{_API_BASE}/repos/{self._owner}/{self._repo}{path}"

    async def _get(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(self._url(path), headers=self._headers, params=params)
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitHub request to {path!r} failed: {exc}") from exc

    async def get_default_branch(self) -> str:
        response = await self._get("")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitHub repository lookup failed: HTTP {response.status_code}")
        return str(response.json()["default_branch"])

    async def list_branches(self) -> list[GitBranch]:
        response = await self._get("/branches")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitHub branch listing failed: HTTP {response.status_code}")
        return [
            GitBranch(name=item["name"], commit_sha=item["commit"]["sha"])
            for item in response.json()
        ]

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        response = await self._get("/commits", params={"sha": branch, "per_page": limit})
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitHub commit listing failed: HTTP {response.status_code}")
        return [
            GitCommit(
                sha=item["sha"],
                message=item["commit"]["message"],
                author=item["commit"]["author"]["name"],
            )
            for item in response.json()
        ]

    async def get_file_content(self, path: str, *, ref: str) -> str | None:
        response = await self._get(f"/contents/{path}", params={"ref": ref})
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitHub file lookup failed: HTTP {response.status_code}")
        return base64.b64decode(response.json()["content"]).decode("utf-8")

    async def sync_file(
        self, path: str, content: str, *, branch: str, message: str
    ) -> GitSyncResult:
        existing = await self._get(f"/contents/{path}", params={"ref": branch})
        body: dict[str, object] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        created = existing.status_code == httpx.codes.NOT_FOUND
        if not created:
            if existing.status_code != httpx.codes.OK:
                raise GitOpsError(f"GitHub file lookup failed: HTTP {existing.status_code}")
            body["sha"] = existing.json()["sha"]

        try:
            response = await self._client.put(
                self._url(f"/contents/{path}"), headers=self._headers, json=body
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitHub file sync failed: {exc}") from exc
        if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GitOpsError(f"GitHub file sync failed: HTTP {response.status_code}")
        return GitSyncResult(commit_sha=response.json()["commit"]["sha"], created=created)

    async def create_pull_request(
        self, *, title: str, head_branch: str, base_branch: str, body: str
    ) -> GitPullRequest:
        try:
            response = await self._client.post(
                self._url("/pulls"),
                headers=self._headers,
                json={"title": title, "head": head_branch, "base": base_branch, "body": body},
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitHub pull request creation failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(f"GitHub pull request creation failed: HTTP {response.status_code}")
        payload = response.json()
        return GitPullRequest(
            number=payload["number"], url=payload["html_url"], state=payload["state"]
        )


__all__ = ["GitHubClient"]
