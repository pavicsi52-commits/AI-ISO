"""Tests for :mod:`app.collectors.synthetic` -- dispatches a
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`'s
own ``check_type`` onto the collector logic that actually performs it.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.validation import ValidationError

from app.collectors.context import CollectorContext
from app.collectors.synthetic import run_synthetic_test
from app.models.enums import MonitoringTargetType, SyntheticCheckType
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.models.monitoring_target import MonitoringTarget
from tests.conftest import AUTOMATION_SERVICE_BASE_URL, build_collector_context


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield build_collector_context(client)


def _test(
    check_type: SyntheticCheckType, *, parameters: dict[str, object] | None = None
) -> MonitoringSyntheticTest:
    return MonitoringSyntheticTest(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        check_type=check_type,
        name="test-synthetic",
        parameters=parameters or {},
    )


def _target(*, host: str = "127.0.0.1") -> MonitoringTarget:
    return MonitoringTarget(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        target_type=MonitoringTargetType.APPLICATION,
        external_id=str(uuid.uuid4()),
        name="test-target",
        target_metadata={"host": host},
    )


@pytest.fixture
async def tcp_server() -> AsyncIterator[int]:
    async def _handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port


class TestHttpAndApi:
    async def test_http_success(self, httpx_mock: HTTPXMock, context: CollectorContext) -> None:
        httpx_mock.add_response(url="http://example.internal/ping", json={"ok": True})
        test = _test(SyntheticCheckType.HTTP, parameters={"url": "http://example.internal/ping"})
        data = await run_synthetic_test(test, None, context)
        assert data["reachable"] is True

    async def test_api_success(self, httpx_mock: HTTPXMock, context: CollectorContext) -> None:
        httpx_mock.add_response(url="http://example.internal/api", json={"ok": True})
        test = _test(SyntheticCheckType.API, parameters={"url": "http://example.internal/api"})
        data = await run_synthetic_test(test, None, context)
        assert data["reachable"] is True

    async def test_missing_url_raises(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.HTTP)
        with pytest.raises(ValidationError, match="url"):
            await run_synthetic_test(test, None, context)


class TestTcp:
    async def test_reachable_port(self, tcp_server: int, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.TCP, parameters={"port": tcp_server})
        data = await run_synthetic_test(test, _target(), context)
        assert data["reachable"] is True

    async def test_missing_host_raises(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.TCP, parameters={"port": 443})
        with pytest.raises(ValidationError, match="host"):
            await run_synthetic_test(test, None, context)

    async def test_host_from_own_parameters(
        self, tcp_server: int, context: CollectorContext
    ) -> None:
        test = _test(SyntheticCheckType.TCP, parameters={"host": "127.0.0.1", "port": tcp_server})
        data = await run_synthetic_test(test, None, context)
        assert data["reachable"] is True


class TestDns:
    async def test_resolves_localhost(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.DNS)
        data = await run_synthetic_test(test, _target(host="localhost"), context)
        assert data["resolved"] is True


class TestAutomationDelegated:
    @pytest.mark.parametrize(
        "check_type",
        [SyntheticCheckType.SSH, SyntheticCheckType.DATABASE, SyntheticCheckType.CUSTOM_SCRIPT],
    )
    async def test_delegates_to_automation(
        self,
        check_type: SyntheticCheckType,
        httpx_mock: HTTPXMock,
        context: CollectorContext,
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        target = _target()
        test = _test(check_type, parameters={"job_id": str(job_id)})
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={"data": {"id": execution_id, "status": "completed", "result": {"ok": True}}},
        )
        data = await run_synthetic_test(test, target, context)
        assert data == {"ok": True}

    async def test_missing_job_id_raises(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.SSH)
        with pytest.raises(ValidationError, match="job_id"):
            await run_synthetic_test(test, _target(), context)

    async def test_no_target_and_no_explicit_id_raises(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.SSH, parameters={"job_id": str(uuid.uuid4())})
        with pytest.raises(ValidationError, match="target_external_id"):
            await run_synthetic_test(test, None, context)

    async def test_explicit_target_external_id_used_without_target(
        self, httpx_mock: HTTPXMock, context: CollectorContext
    ) -> None:
        job_id = uuid.uuid4()
        execution_id = str(uuid.uuid4())
        test = _test(
            SyntheticCheckType.DATABASE,
            parameters={"job_id": str(job_id), "target_external_id": "external-db-1"},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
            method="POST",
            status_code=201,
            json={"data": {"id": execution_id, "status": "pending"}},
        )
        httpx_mock.add_response(
            url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
            json={"data": {"id": execution_id, "status": "completed", "result": {"ok": True}}},
        )
        data = await run_synthetic_test(test, None, context)
        assert data == {"ok": True}


class TestUnsupportedCheckType:
    async def test_raises_for_unmapped_check_type(self, context: CollectorContext) -> None:
        test = _test(SyntheticCheckType.HTTP)
        test.check_type = "not-a-real-check-type"  # type: ignore[assignment]
        with pytest.raises(ValidationError, match="unsupported check_type"):
            await run_synthetic_test(test, None, context)
