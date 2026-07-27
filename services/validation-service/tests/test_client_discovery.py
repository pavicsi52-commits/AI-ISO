"""Tests for :class:`app.clients.discovery_client.DiscoveryClient`
against real documented Discovery Service response shapes, via
``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.discovery_client import DiscoveryClient
from tests.conftest import DISCOVERY_SERVICE_BASE_URL


@pytest.fixture
async def discovery_client() -> AsyncIterator[DiscoveryClient]:
    async with httpx.AsyncClient() as client:
        yield DiscoveryClient(client, base_url=DISCOVERY_SERVICE_BASE_URL, caller_token="tok")


class TestDiscoveryClient:
    async def test_get_job_returns_summary(
        self, httpx_mock: HTTPXMock, discovery_client: DiscoveryClient
    ) -> None:
        job_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{DISCOVERY_SERVICE_BASE_URL}/discovery/jobs/{job_id}",
            json={
                "data": {
                    "id": str(job_id),
                    "status": "completed",
                    "discovered_asset_count": 12,
                    "discovered_relationship_count": 5,
                }
            },
        )
        job = await discovery_client.get_job(job_id)
        assert job["discovered_asset_count"] == 12

    async def test_get_job_missing_raises(
        self, httpx_mock: HTTPXMock, discovery_client: DiscoveryClient
    ) -> None:
        job_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{DISCOVERY_SERVICE_BASE_URL}/discovery/jobs/{job_id}", status_code=404
        )
        with pytest.raises(DependencyError, match="HTTP 404"):
            await discovery_client.get_job(job_id)

    async def test_get_job_unreachable_raises(
        self, httpx_mock: HTTPXMock, discovery_client: DiscoveryClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await discovery_client.get_job(uuid.uuid4())
