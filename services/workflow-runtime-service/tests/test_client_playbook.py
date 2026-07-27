"""Tests for :class:`app.clients.playbook_client.PlaybookClient` against
real documented Playbook Service response shapes, via ``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.playbook_client import PlaybookClient
from tests.conftest import PLAYBOOK_SERVICE_BASE_URL


@pytest.fixture
async def playbook_client() -> AsyncIterator[PlaybookClient]:
    async with httpx.AsyncClient() as client:
        yield PlaybookClient(client, base_url=PLAYBOOK_SERVICE_BASE_URL, caller_token="tok")


class TestPlaybookClient:
    async def test_get_latest_version_found(
        self, httpx_mock: HTTPXMock, playbook_client: PlaybookClient
    ) -> None:
        playbook_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{PLAYBOOK_SERVICE_BASE_URL}/playbooks/{playbook_id}/versions",
            json={"data": [{"id": "v1", "content": "echo hi"}]},
        )
        version = await playbook_client.get_latest_version(playbook_id)
        assert version["content"] == "echo hi"

    async def test_get_latest_version_empty_raises(
        self, httpx_mock: HTTPXMock, playbook_client: PlaybookClient
    ) -> None:
        playbook_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{PLAYBOOK_SERVICE_BASE_URL}/playbooks/{playbook_id}/versions", json={"data": []}
        )
        with pytest.raises(DependencyError, match="no version"):
            await playbook_client.get_latest_version(playbook_id)

    async def test_get_latest_version_server_error_raises(
        self, httpx_mock: HTTPXMock, playbook_client: PlaybookClient
    ) -> None:
        playbook_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{PLAYBOOK_SERVICE_BASE_URL}/playbooks/{playbook_id}/versions", status_code=500
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await playbook_client.get_latest_version(playbook_id)

    async def test_get_latest_version_unreachable_raises(
        self, httpx_mock: HTTPXMock, playbook_client: PlaybookClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await playbook_client.get_latest_version(uuid.uuid4())
