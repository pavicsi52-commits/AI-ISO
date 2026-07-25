"""Regression tests for the discovery-job queue-consumer worker.

Proactively verifies the same commit-visibility bug class every prior
AI-IOS worker test file in this monorepo caught live (first
``services/project-service``'s own ``test_worker_regression.py``, most
recently ``services/inventory-service``'s own ``test_workers.py``):
(1) ``create_job()`` must commit before returning, since the HTTP
handler publishes to the queue immediately after; (2) the worker's own
service factory must durably commit, not just flush, so an independent
session/connection can see the completed job.

Proving either needs two genuinely independent connections -- the usual
``db_session`` fixture is a single SAVEPOINT inside one never-committed
outer transaction, which can't demonstrate cross-connection visibility
-- so this file builds its own plain (non-SAVEPOINT) session factory
directly on ``pg_engine`` and cleans up everything it writes.

Runs a real ``TcpScanner`` probe against the docker-compose Redis
container's host-mapped port (``localhost:6379``, always up in this
environment) end to end through :class:`~app.services.discovery_execution
.DiscoveryExecutionService`, with ``caller_token=None`` -- exercising
the documented scheduler-triggered-run code path (see that service's
own module docstring) without needing a live
secrets-management-service/inventory-service to be running.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest_asyncio
from httpx import AsyncClient
from shared_core.database.session import session_scope
from shared_core.enums.job_status import JobStatus
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from tests.conftest import build_execution_service

from app.models.discovery_audit import DiscoveryAuditEntry
from app.models.discovery_job import DiscoveryJob
from app.models.discovery_profile import DiscoveryProfile
from app.models.discovery_target import DiscoveryTarget
from app.models.enums import DiscoveryMode, ProfileType, ProtocolType, TargetType
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_profile import DiscoveryProfileRepository
from app.repositories.discovery_target import DiscoveryTargetRepository
from app.services.discovery_execution import DiscoveryExecutionService
from app.services.job import DiscoveryJobService
from app.services.profile import DiscoveryProfileService
from app.services.target import DiscoveryTargetService
from app.workers.discovery_worker import ExecutionServiceFactory, build_discovery_worker

RealSessionFactory = tuple[async_sessionmaker[AsyncSession], list[uuid.UUID], list[uuid.UUID]]
"""``(session_factory, created_job_ids, created_profile_ids)`` -- the
latter two are mutated by tests so the fixture's own teardown can clean
them up. Every ``discovery_results``/``discovery_assets``/
``discovery_relationships``/``discovery_failures``/``discovery_history``
row a job produces cascades on the job's own deletion; only
``discovery_audit`` (``ondelete="SET NULL"``, not ``CASCADE`` -- see
``app/models/discovery_audit.py``) and ``discovery_targets`` need
explicit cleanup here.
"""


@pytest_asyncio.fixture
async def real_session_factory(pg_engine: AsyncEngine) -> AsyncIterator[RealSessionFactory]:
    """A plain session factory bound directly to the engine -- i.e.
    exactly what ``create_database_framework`` hands the real app as
    ``database.session_factory``, with no SAVEPOINT/rollback safety net.
    """
    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    created_job_ids: list[uuid.UUID] = []
    created_profile_ids: list[uuid.UUID] = []
    yield factory, created_job_ids, created_profile_ids
    async with factory() as cleanup_session:
        if created_job_ids:
            await cleanup_session.execute(
                delete(DiscoveryAuditEntry).where(DiscoveryAuditEntry.job_id.in_(created_job_ids))
            )
            await cleanup_session.execute(
                delete(DiscoveryTarget).where(DiscoveryTarget.profile_id.in_(created_profile_ids))
            )
            await cleanup_session.execute(
                delete(DiscoveryJob).where(DiscoveryJob.id.in_(created_job_ids))
            )
        if created_profile_ids:
            await cleanup_session.execute(
                delete(DiscoveryProfile).where(DiscoveryProfile.id.in_(created_profile_ids))
            )
        await cleanup_session.commit()


def _execution_service_factory(
    session_factory: async_sessionmaker[AsyncSession], http_client: AsyncClient
) -> ExecutionServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[DiscoveryExecutionService]:
        async with session_scope(session_factory) as session:
            yield build_execution_service(session, http_client)

    return _build


async def _seed_profile_and_target(
    factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    address: str,
    port: int,
) -> uuid.UUID:
    """Create a profile and one TCP target under it, committed for real."""
    async with factory() as session:
        profiles = DiscoveryProfileService(DiscoveryProfileRepository(session))
        targets = DiscoveryTargetService(DiscoveryTargetRepository(session))
        profile = await profiles.create(
            organization_id=organization_id,
            name=f"worker-test-{uuid.uuid4()}",
            description=None,
            profile_type=ProfileType.CUSTOM,
            protocols=[ProtocolType.TCP],
            default_ports={},
            timeout_seconds=30,
            concurrency_limit=10,
        )
        await session.flush()
        await targets.create(
            organization_id=organization_id,
            profile_id=profile.id,
            target_type=TargetType.HOST,
            address=address,
            protocol=ProtocolType.TCP,
            port=port,
        )
        await session.commit()
        return profile.id


async def test_create_job_commits_before_returning(
    real_session_factory: RealSessionFactory,
) -> None:
    """Immediately after ``create_job()`` returns -- before any worker
    ever touches the row -- an independent session must already see it.
    This is exactly the window between ``create_job()`` returning and
    ``producer.publish()`` firing in the real HTTP handler.
    """
    factory, created_job_ids, created_profile_ids = real_session_factory
    org_id = uuid.uuid4()
    profile_id = await _seed_profile_and_target(
        factory, organization_id=org_id, address="localhost", port=6379
    )
    created_profile_ids.append(profile_id)

    async with factory() as session:
        jobs = DiscoveryJobService(
            DiscoveryJobRepository(session), DiscoveryTargetRepository(session), session
        )
        job = await jobs.create_job(
            organization_id=org_id,
            profile_id=profile_id,
            mode=DiscoveryMode.MANUAL,
            triggered_by=None,
        )
    created_job_ids.append(job.id)

    async with factory() as independent_session:
        found = await DiscoveryJobRepository(independent_session).get_by_id(job.id)
    assert found is not None
    assert found.id == job.id
    assert found.status == JobStatus.QUEUED


async def test_worker_completes_job_visibly_to_an_independent_session(
    real_session_factory: RealSessionFactory, real_http_client: AsyncClient
) -> None:
    """The worker handler must leave the job ``COMPLETED``, with a real
    ``DiscoveryResult``/``DiscoveryAsset`` recorded, in a way a
    *separate* session/connection can see -- not just the session the
    worker happened to run on. Probes the docker-compose Redis
    container's host-mapped ``localhost:6379`` for real.
    """
    factory, created_job_ids, created_profile_ids = real_session_factory
    org_id = uuid.uuid4()
    profile_id = await _seed_profile_and_target(
        factory, organization_id=org_id, address="localhost", port=6379
    )
    created_profile_ids.append(profile_id)

    async with factory() as session:
        jobs = DiscoveryJobService(
            DiscoveryJobRepository(session), DiscoveryTargetRepository(session), session
        )
        job = await jobs.create_job(
            organization_id=org_id,
            profile_id=profile_id,
            mode=DiscoveryMode.MANUAL,
            triggered_by=None,
        )
    created_job_ids.append(job.id)

    factory_cm = _execution_service_factory(factory, real_http_client)
    handler = build_discovery_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as independent_session:
        found = await DiscoveryJobRepository(independent_session).get_by_id(job.id)
    assert found is not None
    assert found.status == JobStatus.COMPLETED
    assert found.succeeded_targets == 1
    assert found.failed_targets == 0
    assert found.discovered_asset_count == 1


async def test_worker_marks_job_failed_when_every_target_fails(
    real_session_factory: RealSessionFactory, real_http_client: AsyncClient
) -> None:
    """A target that can never succeed (nothing listens on this port)
    must leave the overall job ``FAILED``, not silently ``COMPLETED``.
    """
    factory, created_job_ids, created_profile_ids = real_session_factory
    org_id = uuid.uuid4()
    profile_id = await _seed_profile_and_target(
        factory, organization_id=org_id, address="localhost", port=1
    )
    created_profile_ids.append(profile_id)

    async with factory() as session:
        jobs = DiscoveryJobService(
            DiscoveryJobRepository(session), DiscoveryTargetRepository(session), session
        )
        job = await jobs.create_job(
            organization_id=org_id,
            profile_id=profile_id,
            mode=DiscoveryMode.MANUAL,
            triggered_by=None,
        )
    created_job_ids.append(job.id)

    factory_cm = _execution_service_factory(factory, real_http_client)
    handler = build_discovery_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as independent_session:
        found = await DiscoveryJobRepository(independent_session).get_by_id(job.id)
    assert found is not None
    assert found.status == JobStatus.FAILED
    assert found.error_summary is not None
