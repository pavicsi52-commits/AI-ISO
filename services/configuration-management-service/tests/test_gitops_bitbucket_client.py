"""Tests for :class:`app.gitops.bitbucket_client.BitbucketClient`."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from app.gitops.base import GitOpsError
from app.gitops.bitbucket_client import BitbucketClient

_BASE = "https://api.bitbucket.org/2.0/repositories/acme/webapp"


@pytest_asyncio.fixture
async def bitbucket_client() -> AsyncIterator[BitbucketClient]:
    async with httpx.AsyncClient() as http_client:
        yield BitbucketClient(http_client, workspace="acme", repo_slug="webapp", token="tok")


async def test_get_default_branch(httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient) -> None:
    httpx_mock.add_response(url=_BASE, json={"mainbranch": {"name": "main"}})
    assert await bitbucket_client.get_default_branch() == "main"


async def test_get_default_branch_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=_BASE, status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.get_default_branch()


async def test_list_branches(httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/refs/branches",
        json={"values": [{"name": "main", "target": {"hash": "abc"}}]},
    )
    branches = await bitbucket_client.list_branches()
    assert branches[0].name == "main"
    assert branches[0].commit_sha == "abc"


async def test_list_branches_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/refs/branches", status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.list_branches()


async def test_list_commits(httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/commits/main?pagelen=20",
        json={
            "values": [
                {"hash": "abc123", "message": "Initial", "author": {"raw": "Ada <ada@x.com>"}}
            ]
        },
    )
    commits = await bitbucket_client.list_commits("main")
    assert commits[0].sha == "abc123"
    assert commits[0].author == "Ada <ada@x.com>"


async def test_list_commits_error(httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/commits/main?pagelen=20", status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.list_commits("main")


async def test_get_file_content_missing(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", status_code=404)
    assert await bitbucket_client.get_file_content("a.txt", ref="main") is None


async def test_get_file_content_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.get_file_content("a.txt", ref="main")


async def test_get_file_content_returns_raw_text(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", text="raw content")
    content = await bitbucket_client.get_file_content("a.txt", ref="main")
    assert content == "raw content"


async def test_sync_file_creates_when_missing(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/src", status_code=201)
    httpx_mock.add_response(
        url=f"{_BASE}/commits/main?pagelen=1",
        json={"values": [{"hash": "new-sha", "message": "m", "author": {"raw": "a"}}]},
    )
    result = await bitbucket_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is True
    assert result.commit_sha == "new-sha"


async def test_sync_file_write_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{_BASE}/src", status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_sync_file_lookup_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}/src/main/a.txt", status_code=500)
    with pytest.raises(GitOpsError):
        await bitbucket_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_create_pull_request(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/pullrequests",
        json={
            "id": 9,
            "links": {"html": {"href": "https://bitbucket.org/acme/webapp/pull-requests/9"}},
            "state": "OPEN",
        },
        status_code=201,
    )
    pr = await bitbucket_client.create_pull_request(
        title="Sync", head_branch="feature", base_branch="main", body="Body"
    )
    assert pr.number == 9
    assert pr.state == "OPEN"


async def test_create_pull_request_error(
    httpx_mock: HTTPXMock, bitbucket_client: BitbucketClient
) -> None:
    httpx_mock.add_response(method="POST", url=f"{_BASE}/pullrequests", status_code=400)
    with pytest.raises(GitOpsError):
        await bitbucket_client.create_pull_request(
            title="Sync", head_branch="feature", base_branch="main", body="Body"
        )
