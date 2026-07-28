"""Tests for :class:`app.clients.validation_client.ValidationClient`
against real documented Validation Service response shapes, via
``pytest-httpx``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.dependency import DependencyError

from app.clients.validation_client import ValidationClient
from tests.conftest import VALIDATION_SERVICE_BASE_URL


@pytest.fixture
async def validation_client() -> AsyncIterator[ValidationClient]:
    async with httpx.AsyncClient() as client:
        yield ValidationClient(client, base_url=VALIDATION_SERVICE_BASE_URL, caller_token="tok")


class TestGetResultsForTarget:
    async def test_returns_results(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        target_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results?target_id={target_id}",
            json={"data": [{"id": str(uuid.uuid4()), "status": "failed"}]},
        )
        results = await validation_client.get_results_for_target(target_id)
        assert results[0]["status"] == "failed"

    async def test_failure_raises(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        target_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results?target_id={target_id}",
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await validation_client.get_results_for_target(target_id)

    async def test_unreachable_raises(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(DependencyError, match="unreachable"):
            await validation_client.get_results_for_target(uuid.uuid4())


class TestGetExecutionScore:
    async def test_returns_score(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        execution_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results/executions/"
            f"{execution_id}/score",
            json={"data": {"overall_score": 0.9}},
        )
        score = await validation_client.get_execution_score(execution_id)
        assert score is not None
        assert score["overall_score"] == 0.9

    async def test_no_score_returns_none(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        execution_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results/executions/"
            f"{execution_id}/score",
            status_code=404,
        )
        score = await validation_client.get_execution_score(execution_id)
        assert score is None

    async def test_failure_raises(
        self, httpx_mock: HTTPXMock, validation_client: ValidationClient
    ) -> None:
        execution_id = uuid.uuid4()
        httpx_mock.add_response(
            url=f"{VALIDATION_SERVICE_BASE_URL}/validation-results/executions/"
            f"{execution_id}/score",
            status_code=500,
        )
        with pytest.raises(DependencyError, match="HTTP 500"):
            await validation_client.get_execution_score(execution_id)
