"""Tests for :class:`app.gitops.gitea_client.GiteaClient`."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from app.gitops.base import GitOpsError
from app.gitops.gitea_client import GiteaClient

_BASE = "https://gitea.internal/api/v1/repos/acme/webapp"


@pytest_asyncio.fixture
async def gitea_client() -> AsyncIterator[GiteaClient]:
    async with httpx.AsyncClient() as http_client:
        yield GiteaClient(
            http_client,
            base_url="https://gitea.internal",
            owner="acme",
            repo="webapp",
            token="tok",
        )


async def test_get_default_branch(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=_BASE, json={"default_branch": "main"})
    assert await gitea_client.get_default_branch() == "main"


async def test_get_default_branch_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=_BASE, status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.get_default_branch()


async def test_list_branches(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/branches", json=[{"name": "main", "commit": {"id": "abc"}}]
    )
    branches = await gitea_client.list_branches()
    assert branches[0].name == "main"
    assert branches[0].commit_sha == "abc"


async def test_list_branches_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/branches", status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.list_branches()


async def test_list_commits(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/commits?sha=main&limit=20",
        json=[{"sha": "abc123", "commit": {"message": "Initial", "author": {"name": "Ada"}}}],
    )
    commits = await gitea_client.list_commits("main")
    assert commits[0].sha == "abc123"
    assert commits[0].author == "Ada"


async def test_list_commits_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/commits?sha=main&limit=20", status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.list_commits("main")


async def test_get_file_content_missing(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", status_code=404)
    assert await gitea_client.get_file_content("a.txt", ref="main") is None


async def test_get_file_content_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.get_file_content("a.txt", ref="main")


async def test_get_file_content_decodes_base64(
    httpx_mock: HTTPXMock, gitea_client: GiteaClient
) -> None:
    encoded = base64.b64encode(b"hello").decode("ascii")
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", json={"content": encoded})
    assert await gitea_client.get_file_content("a.txt", ref="main") == "hello"


async def test_sync_file_creates_when_missing(
    httpx_mock: HTTPXMock, gitea_client: GiteaClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", status_code=404)
    httpx_mock.add_response(
        method="POST", url=f"{_BASE}/contents/a.txt", json={"commit": {"sha": "new-sha"}}
    )
    result = await gitea_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is True
    assert result.commit_sha == "new-sha"


async def test_sync_file_updates_when_present(
    httpx_mock: HTTPXMock, gitea_client: GiteaClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", json={"sha": "old-sha"})
    httpx_mock.add_response(
        method="PUT", url=f"{_BASE}/contents/a.txt", json={"commit": {"sha": "upd-sha"}}
    )
    result = await gitea_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is False
    assert result.commit_sha == "upd-sha"


async def test_sync_file_lookup_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_sync_file_write_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/contents/a.txt?ref=main", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/contents/a.txt", status_code=500)
    with pytest.raises(GitOpsError):
        await gitea_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_create_pull_request(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/pulls",
        json={
            "number": 2,
            "html_url": "https://gitea.internal/acme/webapp/pulls/2",
            "state": "open",
        },
        status_code=201,
    )
    pr = await gitea_client.create_pull_request(
        title="Sync", head_branch="feature", base_branch="main", body="Body"
    )
    assert pr.number == 2
    assert pr.state == "open"


async def test_create_pull_request_error(httpx_mock: HTTPXMock, gitea_client: GiteaClient) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE}/pulls", status_code=422)
    with pytest.raises(GitOpsError):
        await gitea_client.create_pull_request(
            title="Sync", head_branch="feature", base_branch="main", body="Body"
        )
