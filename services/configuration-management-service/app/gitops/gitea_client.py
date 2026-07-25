"""Gitea, via direct REST API v1 calls (``httpx``).

Gitea's own API is deliberately modeled after GitHub's (same base64-blob
content endpoint, same SHA-based optimistic write), so this client
mirrors :class:`app.gitops.github_client.GitHubClient` almost exactly;
the differences are the base path (``/api/v1`` vs. no prefix), the auth
header (``token <token>`` vs. ``Bearer <token>``), and the pull-request
payload's field names (``head``/``base`` vs. GitHub's identical names,
but wrapped without a leading owner qualifier). Gitea is the one
provider genuinely exercised against a real, locally-run Docker
container in this service's own test suite (matching
``services/discovery-service``'s AWS/moto precedent), since it is the
only provider self-hostable without an external account.
"""

from __future__ import annotations

import base64

import httpx

from app.gitops.base import GitBranch, GitCommit, GitOpsError, GitPullRequest, GitSyncResult


class GiteaClient:
    """A thin, real REST client for one Gitea repository."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        owner: str,
        repo: str,
        token: str,
    ) -> None:
        self._client = client
        self._api_base = f"{base_url.rstrip('/')}/api/v1"
        self._owner = owner
        self._repo = repo
        self._headers = {"Authorization": f"token {token}"}

    def _url(self, path: str) -> str:
        return f"{self._api_base}/repos/{self._owner}/{self._repo}{path}"

    async def _get(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(self._url(path), headers=self._headers, params=params)
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Gitea request to {path!r} failed: {exc}") from exc

    async def get_default_branch(self) -> str:
        response = await self._get("")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Gitea repository lookup failed: HTTP {response.status_code}")
        return str(response.json()["default_branch"])

    async def list_branches(self) -> list[GitBranch]:
        response = await self._get("/branches")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Gitea branch listing failed: HTTP {response.status_code}")
        return [
            GitBranch(name=item["name"], commit_sha=item["commit"]["id"])
            for item in response.json()
        ]

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        response = await self._get("/commits", params={"sha": branch, "limit": limit})
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Gitea commit listing failed: HTTP {response.status_code}")
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
            raise GitOpsError(f"Gitea file lookup failed: HTTP {response.status_code}")
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
        try:
            if created:
                response = await self._client.post(
                    self._url(f"/contents/{path}"), headers=self._headers, json=body
                )
            else:
                if existing.status_code != httpx.codes.OK:
                    raise GitOpsError(f"Gitea file lookup failed: HTTP {existing.status_code}")
                body["sha"] = existing.json()["sha"]
                response = await self._client.put(
                    self._url(f"/contents/{path}"), headers=self._headers, json=body
                )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Gitea file sync failed: {exc}") from exc
        if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GitOpsError(f"Gitea file sync failed: HTTP {response.status_code}")
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
            raise GitOpsError(f"Gitea pull request creation failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(f"Gitea pull request creation failed: HTTP {response.status_code}")
        payload = response.json()
        return GitPullRequest(
            number=payload["number"], url=payload["html_url"], state=payload["state"]
        )


__all__ = ["GiteaClient"]
