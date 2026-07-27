"""Tests for :func:`app.workers.execution_worker.build_execution_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from shared_core.exceptions.database import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationExecutionStatus
from app.repositories.validation_execution import ValidationExecutionRepository
from app.services.execution import ValidationExecutionService
from app.workers.execution_worker import build_execution_worker
from tests.conftest import build_execution_service, make_execution, make_profile, make_target


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def test_execution_worker_runs_execution_to_completion(
    db_session: AsyncSession, http_client: httpx.AsyncClient
) -> None:
    org_id = uuid.uuid4()
    profile = await make_profile(db_session, organization_id=org_id)
    target = await make_target(db_session, organization_id=org_id)
    execution = await make_execution(db_session, profile, [target])

    service = build_execution_service(db_session, http_client=http_client)

    @asynccontextmanager
    async def factory() -> AsyncIterator[ValidationExecutionService]:
        yield service

    handler = build_execution_worker(factory)
    await handler({"execution_id": str(execution.id), "caller_token": "tok"})

    refetched = await ValidationExecutionRepository(db_session).require_by_id(execution.id)
    assert refetched.status == ValidationExecutionStatus.PASSED


async def test_execution_worker_skips_when_no_caller_token(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    profile = await make_profile(db_session, organization_id=org_id)
    target = await make_target(db_session, organization_id=org_id)
    execution = await make_execution(db_session, profile, [target])

    @asynccontextmanager
    async def factory() -> AsyncIterator[ValidationExecutionService]:
        raise AssertionError("should never be reached when caller_token is missing")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_execution_worker(factory)
    await handler({"execution_id": str(execution.id), "caller_token": None})

    refetched = await ValidationExecutionRepository(db_session).require_by_id(execution.id)
    assert refetched.status == ValidationExecutionStatus.QUEUED


async def test_execution_worker_reraises_on_failure() -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[ValidationExecutionService]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_execution_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"execution_id": str(uuid.uuid4()), "caller_token": "tok"})
