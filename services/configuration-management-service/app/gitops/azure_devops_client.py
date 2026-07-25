"""Azure DevOps (Azure Repos), via direct REST API calls (``httpx``),
against the real documented contract -- no ``azure-devops`` SDK
dependency. Azure DevOps authenticates with HTTP Basic auth (an empty
username plus a personal access token as the password), addresses
every endpoint under ``{organization}/{project}/_apis/git/repositories
/{repo}`` with an explicit ``api-version`` query parameter on every
call, and -- unlike GitHub/GitLab/Bitbucket/Gitea's per-file write
endpoints -- writes a file by pushing a full git "push" object
(a ref update plus one commit containing one or more changes) rather
than a single-file PUT.
"""

from __future__ import annotations

import base64

import httpx

from app.gitops.base import GitBranch, GitCommit, GitOpsError, GitPullRequest, GitSyncResult

_API_VERSION = "7.1"


class AzureDevOpsClient:
    """A thin, real REST client for one Azure Repos repository."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        organization: str,
        project: str,
        repo: str,
        token: str,
    ) -> None:
        self._client = client
        self._base = (
            f"https://dev.azure.com/{organization}/{project}" f"/_apis/git/repositories/{repo}"
        )
        credentials = base64.b64encode(f":{token}".encode()).decode("ascii")
        self._headers = {"Authorization": f"Basic {credentials}"}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    async def _get(
        self, path: str, *, params: dict[str, str | int | bool] | None = None
    ) -> httpx.Response:
        query: dict[str, str | int | bool] = {"api-version": _API_VERSION, **(params or {})}
        try:
            return await self._client.get(self._url(path), headers=self._headers, params=query)
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Azure DevOps request to {path!r} failed: {exc}") from exc

    async def get_default_branch(self) -> str:
        response = await self._get("")
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Azure DevOps repository lookup failed: HTTP {response.status_code}")
        ref = str(response.json()["defaultBranch"])
        return ref.removeprefix("refs/heads/")

    async def list_branches(self) -> list[GitBranch]:
        response = await self._get("/refs", params={"filter": "heads/"})
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Azure DevOps branch listing failed: HTTP {response.status_code}")
        return [
            GitBranch(
                name=item["name"].removeprefix("refs/heads/"),
                commit_sha=item["objectId"],
            )
            for item in response.json()["value"]
        ]

    async def list_commits(self, branch: str, *, limit: int = 20) -> list[GitCommit]:
        response = await self._get(
            "/commits",
            params={"searchCriteria.itemVersion.version": branch, "searchCriteria.$top": limit},
        )
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Azure DevOps commit listing failed: HTTP {response.status_code}")
        return [
            GitCommit(
                sha=item["commitId"],
                message=item["comment"],
                author=item["author"]["name"],
            )
            for item in response.json()["value"]
        ]

    async def get_file_content(self, path: str, *, ref: str) -> str | None:
        response = await self._get(
            "/items",
            params={"path": path, "versionDescriptor.version": ref, "includeContent": True},
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Azure DevOps file lookup failed: HTTP {response.status_code}")
        return response.text

    async def _get_branch_head_object_id(self, branch: str) -> str | None:
        response = await self._get("/refs", params={"filter": f"heads/{branch}"})
        if response.status_code != httpx.codes.OK:
            raise GitOpsError(f"Azure DevOps ref lookup failed: HTTP {response.status_code}")
        refs = response.json()["value"]
        return str(refs[0]["objectId"]) if refs else None

    async def sync_file(
        self, path: str, content: str, *, branch: str, message: str
    ) -> GitSyncResult:
        old_object_id = await self._get_branch_head_object_id(branch)
        created = old_object_id is None
        change_type = "add" if created else "edit"
        base_object_id = old_object_id or "0000000000000000000000000000000000000000"

        push_body = {
            "refUpdates": [{"name": f"refs/heads/{branch}", "oldObjectId": base_object_id}],
            "commits": [
                {
                    "comment": message,
                    "changes": [
                        {
                            "changeType": change_type,
                            "item": {"path": path},
                            "newContent": {"content": content, "contentType": "rawtext"},
                        }
                    ],
                }
            ],
        }
        try:
            response = await self._client.post(
                self._url("/pushes"),
                headers=self._headers,
                params={"api-version": _API_VERSION},
                json=push_body,
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Azure DevOps file sync failed: {exc}") from exc
        if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise GitOpsError(f"Azure DevOps file sync failed: HTTP {response.status_code}")
        payload = response.json()
        return GitSyncResult(commit_sha=payload["commits"][0]["commitId"], created=created)

    async def create_pull_request(
        self, *, title: str, head_branch: str, base_branch: str, body: str
    ) -> GitPullRequest:
        try:
            response = await self._client.post(
                self._url("/pullrequests"),
                headers=self._headers,
                params={"api-version": _API_VERSION},
                json={
                    "sourceRefName": f"refs/heads/{head_branch}",
                    "targetRefName": f"refs/heads/{base_branch}",
                    "title": title,
                    "description": body,
                },
            )
        except httpx.HTTPError as exc:
            raise GitOpsError(f"Azure DevOps pull request creation failed: {exc}") from exc
        if response.status_code != httpx.codes.CREATED:
            raise GitOpsError(
                f"Azure DevOps pull request creation failed: HTTP {response.status_code}"
            )
        payload = response.json()
        pr_id = payload["pullRequestId"]
        url = payload.get("url", "")
        return GitPullRequest(number=pr_id, url=url, state=payload["status"])


__all__ = ["AzureDevOpsClient"]
