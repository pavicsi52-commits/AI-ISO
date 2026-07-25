"""Tests for :class:`app.gitops.gitlab_client.GitLabClient`."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from app.gitops.base import GitOpsError
from app.gitops.gitlab_client import GitLabClient

_BASE = "https://gitlab.com/api/v4/projects/acme%2Fwebapp"


@pytest_asyncio.fixture
async def gitlab_client() -> AsyncIterator[GitLabClient]:
    async with httpx.AsyncClient() as http_client:
        yield GitLabClient(http_client, project_id="acme/webapp", token="tok")


async def test_get_default_branch(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=_BASE, json={"default_branch": "main"})
    assert await gitlab_client.get_default_branch() == "main"


async def test_get_default_branch_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=_BASE, status_code=500)
    with pytest.raises(GitOpsError):
        await gitlab_client.get_default_branch()


async def test_list_branches(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/repository/branches",
        json=[{"name": "main", "commit": {"id": "abc"}}],
    )
    branches = await gitlab_client.list_branches()
    assert branches[0].name == "main"
    assert branches[0].commit_sha == "abc"


async def test_list_branches_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/branches", status_code=404)
    with pytest.raises(GitOpsError):
        await gitlab_client.list_branches()


async def test_list_commits(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/repository/commits?ref_name=main&per_page=20",
        json=[{"id": "abc123", "message": "Initial", "author_name": "Ada"}],
    )
    commits = await gitlab_client.list_commits("main")
    assert commits[0].sha == "abc123"
    assert commits[0].author == "Ada"


async def test_list_commits_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/repository/commits?ref_name=main&per_page=20", status_code=500
    )
    with pytest.raises(GitOpsError):
        await gitlab_client.list_commits("main")


async def test_get_file_content_missing(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", status_code=404)
    assert await gitlab_client.get_file_content("a.txt", ref="main") is None


async def test_get_file_content_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", status_code=500)
    with pytest.raises(GitOpsError):
        await gitlab_client.get_file_content("a.txt", ref="main")


async def test_get_file_content_decodes_base64(
    httpx_mock: HTTPXMock, gitlab_client: GitLabClient
) -> None:
    encoded = base64.b64encode(b"hello").decode("ascii")
    httpx_mock.add_response(
        url=f"{_BASE}/repository/files/a.txt?ref=main", json={"content": encoded}
    )
    assert await gitlab_client.get_file_content("a.txt", ref="main") == "hello"


async def test_sync_file_creates_when_missing(
    httpx_mock: HTTPXMock, gitlab_client: GitLabClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/repository/files/a.txt", status_code=201)
    httpx_mock.add_response(
        url=f"{_BASE}/repository/commits?ref_name=main&per_page=1",
        json=[{"id": "new-sha", "message": "m", "author_name": "a"}],
    )
    result = await gitlab_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is True
    assert result.commit_sha == "new-sha"


async def test_sync_file_updates_when_present(
    httpx_mock: HTTPXMock, gitlab_client: GitLabClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", json={"content": "x"})
    httpx_mock.add_response(method="PUT", url=f"{_BASE}/repository/files/a.txt", status_code=200)
    httpx_mock.add_response(
        url=f"{_BASE}/repository/commits?ref_name=main&per_page=1",
        json=[{"id": "upd-sha", "message": "m", "author_name": "a"}],
    )
    result = await gitlab_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is False
    assert result.commit_sha == "upd-sha"


async def test_sync_file_lookup_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", status_code=500)
    with pytest.raises(GitOpsError):
        await gitlab_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_sync_file_write_error(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/repository/files/a.txt?ref=main", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/repository/files/a.txt", status_code=500)
    with pytest.raises(GitOpsError):
        await gitlab_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_create_pull_request(httpx_mock: HTTPXMock, gitlab_client: GitLabClient) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/merge_requests",
        json={
            "iid": 3,
            "web_url": "https://gitlab.com/acme/webapp/-/merge_requests/3",
            "state": "opened",
        },
        status_code=201,
    )
    pr = await gitlab_client.create_pull_request(
        title="Sync", head_branch="feature", base_branch="main", body="Body"
    )
    assert pr.number == 3
    assert pr.state == "opened"


async def test_create_pull_request_error(
    httpx_mock: HTTPXMock, gitlab_client: GitLabClient
) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE}/merge_requests", status_code=422)
    with pytest.raises(GitOpsError):
        await gitlab_client.create_pull_request(
            title="Sync", head_branch="feature", base_branch="main", body="Body"
        )
