"""Live integration test for :class:`app.gitops.gitea_client.GiteaClient`
against a real, locally-run Gitea container.

Gitea is the one Git provider genuinely live-tested in this suite
(self-hostable via Docker, matching AWS/moto's role in
``services/discovery-service``'s own test suite) -- GitHub/GitLab/Azure
DevOps/Bitbucket are tested with ``pytest-httpx`` against their real
documented response shapes instead, since none of those are
self-hostable for a local test run.

Run a Gitea instance to exercise this suite::

    docker run -d --name aiios_configmgmt_test_gitea -p 3080:3000 \\
        -e GITEA__security__INSTALL_LOCK=true \\
        -e GITEA__database__DB_TYPE=sqlite3 gitea/gitea:latest
    docker exec -u git aiios_configmgmt_test_gitea gitea admin user create \\
        --username aiios-test --password TestPass123! \\
        --email aiios-test@example.com --admin --must-change-password=false

Skips automatically when no such instance is reachable at
``AIIOS_TEST_GITEA_BASE_URL`` (default ``http://localhost:3080``).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.gitops.base import GitOpsError
from app.gitops.gitea_client import GiteaClient

_BASE_URL = os.environ.get("AIIOS_TEST_GITEA_BASE_URL", "http://localhost:3080")
_TOKEN = os.environ.get("AIIOS_TEST_GITEA_TOKEN", "")
_OWNER = os.environ.get("AIIOS_TEST_GITEA_OWNER", "aiios-test")
_REPO = os.environ.get("AIIOS_TEST_GITEA_REPO", "webapp")

pytestmark = pytest.mark.skipif(
    not _TOKEN, reason="AIIOS_TEST_GITEA_TOKEN not set; no live Gitea instance configured."
)


@pytest_asyncio.fixture
async def live_gitea_client() -> AsyncIterator[GiteaClient]:
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        client = GiteaClient(
            http_client, base_url=_BASE_URL, owner=_OWNER, repo=_REPO, token=_TOKEN
        )
        try:
            await client.get_default_branch()
        except GitOpsError as exc:
            pytest.skip(f"Gitea at {_BASE_URL} is not reachable: {exc}")
        yield client


async def test_get_default_branch(live_gitea_client: GiteaClient) -> None:
    branch = await live_gitea_client.get_default_branch()
    assert branch


async def test_list_branches_includes_default(live_gitea_client: GiteaClient) -> None:
    default_branch = await live_gitea_client.get_default_branch()
    branches = await live_gitea_client.list_branches()
    assert any(branch.name == default_branch for branch in branches)


async def test_sync_file_create_then_read_back(live_gitea_client: GiteaClient) -> None:
    default_branch = await live_gitea_client.get_default_branch()
    path = f"aiios-live-test-{uuid.uuid4().hex}.json"

    result = await live_gitea_client.sync_file(
        path,
        '{"hello": "world"}',
        branch=default_branch,
        message="AI-IOS live GitOps test: create file.",
    )
    assert result.created is True
    assert result.commit_sha

    content = await live_gitea_client.get_file_content(path, ref=default_branch)
    assert content == '{"hello": "world"}'


async def test_sync_file_update_existing(live_gitea_client: GiteaClient) -> None:
    default_branch = await live_gitea_client.get_default_branch()
    path = f"aiios-live-test-{uuid.uuid4().hex}.json"

    await live_gitea_client.sync_file(path, '{"v": 1}', branch=default_branch, message="create")
    result = await live_gitea_client.sync_file(
        path, '{"v": 2}', branch=default_branch, message="update"
    )
    assert result.created is False

    content = await live_gitea_client.get_file_content(path, ref=default_branch)
    assert content == '{"v": 2}'


async def test_get_file_content_missing_returns_none(live_gitea_client: GiteaClient) -> None:
    default_branch = await live_gitea_client.get_default_branch()
    content = await live_gitea_client.get_file_content(
        f"does-not-exist-{uuid.uuid4().hex}.json", ref=default_branch
    )
    assert content is None


async def test_list_commits_returns_history(live_gitea_client: GiteaClient) -> None:
    default_branch = await live_gitea_client.get_default_branch()
    path = f"aiios-live-test-{uuid.uuid4().hex}.json"
    await live_gitea_client.sync_file(
        path, '{"a": 1}', branch=default_branch, message="AI-IOS live GitOps commit-history test."
    )

    commits = await live_gitea_client.list_commits(default_branch, limit=5)
    assert len(commits) >= 1
    assert any("AI-IOS live GitOps" in commit.message for commit in commits)
