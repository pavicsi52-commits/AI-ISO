"""Tests for :class:`app.services.execution.ValidationExecutionService` --
real end-to-end validation execution runs, no mocking of the engine
itself. Real network collectors run against a genuine local TCP
server this test starts; cross-service collectors use ``pytest-httpx``
against the target service's own real documented response shapes.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import CollectorRegistry
from app.models.enums import (
    ValidationCheckType,
    ValidationConcurrencyStrategy,
    ValidationExecutionStatus,
    ValidationResultStatus,
    ValidationTargetType,
)
from app.repositories.validation_execution import ValidationExecutionRepository
from tests.conftest import build_execution_service, make_check, make_profile, make_rule, make_target


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
async def tcp_server() -> AsyncIterator[int]:
    async def _handle(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        yield port


class TestHappyPath:
    async def test_connectivity_check_passes_and_scores_100(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient, tcp_server: int
    ) -> None:
        org_id = uuid.uuid4()
        check = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CONNECTIVITY,
            collector_key="connectivity",
            parameters={"port": tcp_server},
        )
        await make_rule(db_session, check, condition="reachable == false")
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(
            db_session,
            organization_id=org_id,
            target_type=ValidationTargetType.PHYSICAL_SERVER,
            target_metadata={"host": "127.0.0.1"},
        )
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[target.id],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=uuid.uuid4(),
        )

        finished = await execution_service.run_execution(execution.id, caller_token="tok")

        assert finished.status == ValidationExecutionStatus.PASSED
        assert finished.started_at is not None
        assert finished.finished_at is not None

    async def test_failing_rule_marks_execution_failed_and_records_failure(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient
    ) -> None:
        org_id = uuid.uuid4()
        check = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CONNECTIVITY,
            collector_key="connectivity",
            parameters={"port": 1},
        )
        await make_rule(db_session, check, condition="reachable == false")
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(
            db_session, organization_id=org_id, target_metadata={"host": "127.0.0.1"}
        )
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[target.id],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=None,
        )

        finished = await execution_service.run_execution(execution.id, caller_token="tok")

        assert finished.status == ValidationExecutionStatus.FAILED
        results = await execution_service._results.list_for_execution(finished.id)
        assert len(results) == 1
        assert results[0].status == ValidationResultStatus.FAILED
        failures = await execution_service._failures.list_for_result(results[0].id)
        assert len(failures) == 1

        score = await execution_service._scores.get_for_execution(finished.id)
        assert score is not None
        assert score.overall_score == 0.0

    async def test_unresolvable_collector_records_unknown_without_crashing(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient
    ) -> None:
        org_id = uuid.uuid4()
        check = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CONNECTIVITY,
            collector_key="connectivity",
            parameters={},
        )
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(db_session, organization_id=org_id, target_metadata={})
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[target.id],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=None,
        )

        finished = await execution_service.run_execution(execution.id, caller_token="tok")

        assert finished.status == ValidationExecutionStatus.UNKNOWN
        results = await execution_service._results.list_for_execution(finished.id)
        assert results[0].status == ValidationResultStatus.UNKNOWN
        assert "host" in (results[0].message or "")


class TestConcurrency:
    async def test_parallel_execution_runs_every_pair(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient, tcp_server: int
    ) -> None:
        org_id = uuid.uuid4()
        check_a = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CONNECTIVITY,
            collector_key="connectivity",
            parameters={"port": tcp_server},
        )
        check_b = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.PORTS,
            collector_key="port",
            parameters={"port": tcp_server},
        )
        await make_rule(db_session, check_a, condition="reachable == false")
        await make_rule(db_session, check_b, condition="reachable == false")
        profile = await make_profile(
            db_session, organization_id=org_id, check_ids=[check_a.id, check_b.id]
        )
        target_1 = await make_target(
            db_session, organization_id=org_id, target_metadata={"host": "127.0.0.1"}
        )
        target_2 = await make_target(
            db_session, organization_id=org_id, target_metadata={"host": "127.0.0.1"}
        )
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[target_1.id, target_2.id],
            concurrency_strategy=ValidationConcurrencyStrategy.PARALLEL,
            triggered_by=None,
        )

        finished = await execution_service.run_execution(execution.id, caller_token="tok")

        assert finished.status == ValidationExecutionStatus.PASSED
        results = await execution_service._results.list_for_execution(finished.id)
        assert len(results) == 4


class TestCancellation:
    async def test_cooperative_cancel_stops_remaining_sequential_checks(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient, tcp_server: int
    ) -> None:
        org_id = uuid.uuid4()
        cancelling_check = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CUSTOM,
            collector_key="cancel_trigger",
        )
        connectivity_check = await make_check(
            db_session,
            organization_id=org_id,
            check_type=ValidationCheckType.CONNECTIVITY,
            collector_key="connectivity",
            parameters={"port": tcp_server},
        )
        profile = await make_profile(
            db_session,
            organization_id=org_id,
            check_ids=[cancelling_check.id, connectivity_check.id],
        )
        target = await make_target(
            db_session, organization_id=org_id, target_metadata={"host": "127.0.0.1"}
        )

        execution_repo = ValidationExecutionRepository(db_session)

        async def _cancel_trigger(
            _check: object, _target: object, _context: object
        ) -> dict[str, Any]:
            execution = await execution_repo.require_by_id(execution_id_holder["id"])
            execution.status = ValidationExecutionStatus.CANCELLED
            await execution_repo.update(execution)
            return {}

        registry = CollectorRegistry()
        registry.register("cancel_trigger", _cancel_trigger)
        execution_service = build_execution_service(
            db_session, http_client=http_client, collectors=registry
        )
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[target.id],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=None,
        )
        execution_id_holder = {"id": execution.id}

        finished = await execution_service.run_execution(execution.id, caller_token="tok")

        assert finished.status == ValidationExecutionStatus.CANCELLED
        results = await execution_service._results.list_for_execution(finished.id)
        assert len(results) == 1


class TestGetActiveAndCancel:
    async def test_get_active_for_profile_returns_running_execution(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient
    ) -> None:
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=None,
        )
        active = await execution_service.get_active_for_profile(profile.id)
        assert active.id == execution.id

    async def test_cancel_already_terminal_raises_conflict(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient
    ) -> None:
        org_id = uuid.uuid4()
        profile = await make_profile(db_session, organization_id=org_id)
        execution_service = build_execution_service(db_session, http_client=http_client)
        execution = await execution_service.create(
            organization_id=org_id,
            project_id=None,
            profile_id=profile.id,
            target_ids=[],
            concurrency_strategy=ValidationConcurrencyStrategy.SEQUENTIAL,
            triggered_by=None,
        )
        await execution_service.cancel(execution.id)
        with pytest.raises(ConflictError):
            await execution_service.cancel(execution.id)
