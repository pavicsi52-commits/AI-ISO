"""Tests for :class:`app.gitops.azure_devops_client.AzureDevOpsClient`."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from app.gitops.azure_devops_client import AzureDevOpsClient
from app.gitops.base import GitOpsError

_BASE = "https://dev.azure.com/acme-org/acme-project/_apis/git/repositories/webapp"


@pytest_asyncio.fixture
async def azure_client() -> AsyncIterator[AzureDevOpsClient]:
    async with httpx.AsyncClient() as http_client:
        yield AzureDevOpsClient(
            http_client, organization="acme-org", project="acme-project", repo="webapp", token="tok"
        )


async def test_get_default_branch(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}?api-version=7.1", json={"defaultBranch": "refs/heads/main"}
    )
    assert await azure_client.get_default_branch() == "main"


async def test_get_default_branch_error(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(url=f"{_BASE}?api-version=7.1", status_code=500)
    with pytest.raises(GitOpsError):
        await azure_client.get_default_branch()


async def test_list_branches(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/refs?api-version=7.1&filter=heads/",
        json={"value": [{"name": "refs/heads/main", "objectId": "abc"}]},
    )
    branches = await azure_client.list_branches()
    assert branches[0].name == "main"
    assert branches[0].commit_sha == "abc"


async def test_list_branches_error(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(url=f"{_BASE}/refs?api-version=7.1&filter=heads/", status_code=500)
    with pytest.raises(GitOpsError):
        await azure_client.list_branches()


async def test_list_commits(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(
        url=(
            f"{_BASE}/commits?api-version=7.1&searchCriteria.itemVersion.version=main"
            "&searchCriteria.%24top=20"
        ),
        json={"value": [{"commitId": "abc123", "comment": "Initial", "author": {"name": "Ada"}}]},
    )
    commits = await azure_client.list_commits("main")
    assert commits[0].sha == "abc123"
    assert commits[0].author == "Ada"


async def test_get_file_content_missing(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(
        url=(
            f"{_BASE}/items?api-version=7.1&path=a.txt&versionDescriptor.version=main"
            "&includeContent=true"
        ),
        status_code=404,
    )
    assert await azure_client.get_file_content("a.txt", ref="main") is None


async def test_get_file_content_returns_raw_text(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(
        url=(
            f"{_BASE}/items?api-version=7.1&path=a.txt&versionDescriptor.version=main"
            "&includeContent=true"
        ),
        text="raw file content",
    )
    content = await azure_client.get_file_content("a.txt", ref="main")
    assert content == "raw file content"


async def test_sync_file_creates_when_ref_missing(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/refs?api-version=7.1&filter=heads/main", json={"value": []}
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/pushes?api-version=7.1",
        json={"commits": [{"commitId": "new-sha"}]},
        status_code=201,
    )
    result = await azure_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is True
    assert result.commit_sha == "new-sha"


async def test_sync_file_updates_when_ref_exists(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/refs?api-version=7.1&filter=heads/main",
        json={"value": [{"name": "refs/heads/main", "objectId": "old-sha"}]},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/pushes?api-version=7.1",
        json={"commits": [{"commitId": "upd-sha"}]},
        status_code=200,
    )
    result = await azure_client.sync_file("a.txt", "content", branch="main", message="msg")
    assert result.created is False
    assert result.commit_sha == "upd-sha"


async def test_sync_file_push_error(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(
        url=f"{_BASE}/refs?api-version=7.1&filter=heads/main", json={"value": []}
    )
    httpx_mock.add_response(method="POST", url=f"{_BASE}/pushes?api-version=7.1", status_code=500)
    with pytest.raises(GitOpsError):
        await azure_client.sync_file("a.txt", "content", branch="main", message="msg")


async def test_create_pull_request(httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/pullrequests?api-version=7.1",
        json={
            "pullRequestId": 5,
            "url": "https://dev.azure.com/acme-org/acme-project/_apis/git/pr/5",
            "status": "active",
        },
        status_code=201,
    )
    pr = await azure_client.create_pull_request(
        title="Sync", head_branch="feature", base_branch="main", body="Body"
    )
    assert pr.number == 5
    assert pr.state == "active"


async def test_create_pull_request_error(
    httpx_mock: HTTPXMock, azure_client: AzureDevOpsClient
) -> None:
    httpx_mock.add_response(
        method="POST", url=f"{_BASE}/pullrequests?api-version=7.1", status_code=409
    )
    with pytest.raises(GitOpsError):
        await azure_client.create_pull_request(
            title="Sync", head_branch="feature", base_branch="main", body="Body"
        )
