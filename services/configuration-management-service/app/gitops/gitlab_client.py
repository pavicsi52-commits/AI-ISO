"""GitLab, via direct REST API v4 calls (``httpx``), against the real
documented contract -- no ``python-gitlab`` dependency. GitLab addresses
a repository by a numeric or URL-encoded ``namespace/project`` id and
addresses file paths URL-encoded within the path segment itself, unlike
GitHub/Gitea's separate-query-param style.
"""

from __future__ import annotations

import base64
from urllib.parse import quote

import httpx

from app.gitops.base import GitBranch, GitCommit, GitOpsError, GitPullRequest, GitSyncResult

_API_BASE = "https://gitlab.com/api/v4"


class GitLabClient:
    """A thin, real REST client for one GitLab project."""

    def __init__(self, client: httpx.AsyncClient, *, project_id: str, token: str) -> None:
        self._client = client
        self._project = quote(project_id, safe="")
        self._headers = {"PRIVATE-TOKEN": token}

    def _url(self, path: str) -> str:
        return f"{_API_BASE}/projects/{self._project}{path}"

    async def _get(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(self._url(path), headers=self._headers, params=params)
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitLab request to {path!r} failed: {exc}") from exc

    async def get_default_branch(self) -> str:
        response = await self._get("")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitLab project lookup failed: HTTP {response.status_code}")
        return str(response.json()["default_branch"])

    async def list_branches(self) -> list[GitBranch]:
        response = await self._get("/repository/branches")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitLab branch listing failed: HTTP {response.status_code}")
        return [
            GitBranch(name=item["name"], commit_sha=item["commit"]["id"])
            for item in response.json()
        ]

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        response = await self._get(
            "/repository/commits", params={"ref_name": branch, "per_page": limit}
        )
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitLab commit listing failed: HTTP {response.status_code}")
        return [
            GitCommit(sha=item["id"], message=item["message"], author=item["author_name"])
            for item in response.json()
        ]

    async def get_file_content(self, path: str, *, ref: str) -> str | None:
        encoded_path = quote(path, safe="")
        response = await self._get(f"/repository/files/{encoded_path}", params={"ref": ref})
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitLab file lookup failed: HTTP {response.status_code}")
        return base64.b64decode(response.json()["content"]).decode("utf-8")

    async def sync_file(
        self, path: str, content: str, *, branch: str, message: str
    ) -> GitSyncResult:
        encoded_path = quote(path, safe="")
        existing = await self._get(f"/repository/files/{encoded_path}", params={"ref": branch})
        created = existing.status_code == httpx.codes.NOT_FOUND
        if not created and existing.status_code != httpx.codes.OK:
            raise GitOpsError(f"GitLab file lookup failed: HTTP {existing.status_code}")

        body = {"branch": branch, "content": content, "commit_message": message}
        try:
            if created:
                response = await self._client.post(
                    self._url(f"/repository/files/{encoded_path}"),
                    headers=self._headers,
                    json=body,
                )
            else:
                response = await self._client.put(
                    self._url(f"/repository/files/{encoded_path}"),
                    headers=self._headers,
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitLab file sync failed: {exc}") from exc
        if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GitOpsError(f"GitLab file sync failed: HTTP {response.status_code}")

        commits = await self.list_commits(branch, limit=1)
        commit_sha = commits[0].sha if commits else ""
        return GitSyncResult(commit_sha=commit_sha, created=created)

    async def create_pull_request(
        self, *, title: str, head_branch: str, base_branch: str, body: str
    ) -> GitPullRequest:
        try:
            response = await self._client.post(
                self._url("/merge_requests"),
                headers=self._headers,
                json={
                    "title": title,
                    "source_branch": head_branch,
                    "target_branch": base_branch,
                    "description": body,
                },
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"GitLab merge request creation failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(f"GitLab merge request creation failed: HTTP {response.status_code}")
        payload = response.json()
        return GitPullRequest(number=payload["iid"], url=payload["web_url"], state=payload["state"])


__all__ = ["GitLabClient"]
