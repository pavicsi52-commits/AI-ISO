"""Tests for :class:`app.clients.configuration_client.ConfigurationClient`
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

from app.clients.configuration_client import ConfigurationClient
from tests.conftest import CONFIGURATION_SERVICE_BASE_URL


@pytest.fixture
async def configuration_client() -> AsyncIterator[ConfigurationClient]:
    async with httpx.AsyncClient() as client:
        yield ConfigurationClient(
            client, base_url=CONFIGURATION_SERVICE_BASE_URL, caller_token="tok"
        )


class TestConfigurationClient:
    async def test_get_drift_returns_records(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        org_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/drift"
            f"?organization_id={org_id}&profile_id={profile_id}",
            json={"data": [{"id": str(uuid.uuid4()), "resolved_at": None}]},
        )
        records = await configuration_client.get_drift(org_id, profile_id)
        assert len(records) == 1

    async def test_get_drift_failure_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        org_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/drift"
            f"?organization_id={org_id}&profile_id={profile_id}",
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await configuration_client.get_drift(org_id, profile_id)

    async def test_get_drift_unreachable_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await configuration_client.get_drift(uuid.uuid4(), uuid.uuid4())

    async def test_get_compliance_returns_records(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/compliance"
            f"?profile_id={profile_id}",
            json={"data": [{"id": str(uuid.uuid4()), "status": "compliant"}]},
        )
        records = await configuration_client.get_compliance(profile_id)
        assert records[0]["status"] == "compliant"

    async def test_get_compliance_failure_raises(
        self, httpx_mock: HTTPXMock, configuration_client: ConfigurationClient
    ) -> None:
        profile_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{CONFIGURATION_SERVICE_BASE_URL}/configurations/compliance"
            f"?profile_id={profile_id}",
            status_code=404,
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await configuration_client.get_compliance(profile_id)
