"""Tests for :class:`app.dependencies.configuration_client.ConfigurationClient`
against real documented Configuration Management Service response
shapes, via ``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.dependencies.configuration_client import ConfigurationClient
from tests.conftest import CONFIGURATION_SERVICE_BASE_URL


@pytest.fixture
async def configuration_client() -> AsyncIterator[ConfigurationClient]:
    async with httpx.AsyncClient() as client:
        yield ConfigurationClient(client, base_url=CONFIGURATION_SERVICE_BASE_URL)


class TestConfigurationClient:
    async def test_get_profile_found(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}",
            json={"data": {"id": str(profile_id), "profile_name": "p1"}},
        )
        profile = await configuration_client.get_profile(profile_id, caller_token="tok")
        assert profile is not None
        assert profile["profile_name"] == "p1"

    async def test_get_profile_not_found_returns_none(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}", status_code=404
        )
        profile = await configuration_client.get_profile(profile_id, caller_token="tok")
        assert profile is None

    async def test_get_profile_forbidden_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}", status_code=401
        )
        with pytest.raises(DependencyError, match="Not authorized"):
            await configuration_client.get_profile(profile_id, caller_token="tok")

    async def test_get_profile_server_error_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}", status_code=500
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await configuration_client.get_profile(profile_id, caller_token="tok")

    async def test_get_profile_unreachable_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await configuration_client.get_profile(uuid.uuid4(), caller_token="tok")

    async def test_get_latest_version_returns_first(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}/versions",
            json={"data": [{"version_number": 3}, {"version_number": 2}]},
        )
        version = await configuration_client.get_latest_version(profile_id, caller_token="tok")
        assert version is not None
        assert version["version_number"] == 3

    async def test_get_latest_version_no_profile_returns_none(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}/versions",
            status_code=404,
        )
        version = await configuration_client.get_latest_version(profile_id, caller_token="tok")
        assert version is None

    async def test_get_latest_version_empty_list_returns_none(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}/versions",
            json={"data": []},
        )
        version = await configuration_client.get_latest_version(profile_id, caller_token="tok")
        assert version is None

    async def test_get_latest_version_forbidden_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/{profile_id}/versions",
            status_code=403,
        )
        with pytest.raises(DependencyError, match="Not authorized"):
            await configuration_client.get_latest_version(profile_id, caller_token="tok")
