"""Tests for :func:`app.workers.statistics_worker.build_statistics_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from shared_core.exceptions.database import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_version import ConfigurationVersionRepository
from app.services.statistics import ConfigurationStatisticsService
from app.workers.statistics_worker import build_statistics_worker
from tests.conftest import make_profile


async def test_statistics_worker_recomputes_snapshot(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id)

    @asynccontextmanager
    async def factory() -> AsyncIterator[ConfigurationStatisticsService]:
        yield ConfigurationStatisticsService(
            ConfigurationStatisticsRepository(db_session),
            ConfigurationProfileRepository(db_session),
            ConfigurationVersionRepository(db_session),
            ConfigurationDriftRepository(db_session),
            ConfigurationComplianceRepository(db_session),
            ConfigurationRollbackRepository(db_session),
            ConfigurationChangeSetRepository(db_session),
        )

    handler = build_statistics_worker(factory)
    await handler({"organization_id": str(org_id)})

    snapshot = await ConfigurationStatisticsRepository(db_session).get_for_org(org_id)
    assert snapshot is not None
    assert snapshot.total_profiles == 1


async def test_statistics_worker_reraises_on_failure(db_session: AsyncSession) -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[ConfigurationStatisticsService]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_statistics_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"organization_id": str(uuid.uuid4())})
