"""Regression tests for the import/export queue-consumer workers.

Proactively verifies the same two commit-visibility bug classes
``services/project-service``'s own ``test_worker_regression.py`` first
caught live: (1) ``create_job()`` must commit before returning, since
the HTTP handler publishes to the queue immediately after; (2) a
worker's own service factory must durably commit, not just flush, so
an independent session/connection can see the completed job.

Proving either needs two genuinely independent connections -- the
usual ``db_session`` fixture is a single SAVEPOINT inside one
never-committed outer transaction, which can't demonstrate
cross-connection visibility -- so this file builds its own plain
(non-SAVEPOINT) session factory directly on ``pg_engine`` and cleans up
everything it writes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from neo4j import AsyncDriver
from shared_core.database.session import session_scope
from shared_core.enums.job_status import JobStatus
from shared_core.storage import StorageWrapper
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.asset import Asset
from app.models.asset_export_job import AssetExportJob
from app.models.asset_import_job import AssetImportJob
from app.models.enums import AssetType, ExportFormat, ImportFormat
from app.repositories.asset import AssetRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_tag import AssetTagRepository
from app.services.export_service import AssetExportService
from app.services.import_service import AssetImportService
from app.topology.graph import TopologyGraphClient
from app.workers.export_worker import ExportServiceFactory, build_export_worker
from app.workers.import_worker import ImportServiceFactory, build_import_worker
from tests.conftest import build_asset_service

_BUCKET = "inventory-import-export-test"

RealSessionFactory = tuple[async_sessionmaker[AsyncSession], list[uuid.UUID], list[uuid.UUID]]
"""``(session_factory, created_job_ids, created_asset_ids)`` -- the
latter two are mutated by tests so the fixture's own teardown can clean
them up; the Neo4j side of anything an import/export worker touches is
wiped by ``real_neo4j_driver``'s own teardown.
"""


@pytest_asyncio.fixture
async def real_session_factory(pg_engine: AsyncEngine) -> AsyncIterator[RealSessionFactory]:
    """A plain session factory bound directly to the engine -- i.e.
    exactly what ``create_database_framework`` hands the real app as
    ``database.session_factory``, with no SAVEPOINT/rollback safety net.
    """
    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    created_job_ids: list[uuid.UUID] = []
    created_asset_ids: list[uuid.UUID] = []
    yield factory, created_job_ids, created_asset_ids
    async with factory() as cleanup_session:
        if created_job_ids:
            await cleanup_session.execute(
                delete(AssetImportJob).where(AssetImportJob.id.in_(created_job_ids))
            )
            await cleanup_session.execute(
                delete(AssetExportJob).where(AssetExportJob.id.in_(created_job_ids))
            )
        if created_asset_ids:
            await cleanup_session.execute(delete(Asset).where(Asset.id.in_(created_asset_ids)))
        await cleanup_session.commit()


def _import_service_factory(
    session_factory: async_sessionmaker[AsyncSession],
    storage_wrapper: StorageWrapper,
    graph: TopologyGraphClient,
) -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[AssetImportService]:
        async with session_scope(session_factory) as session:
            assets = build_asset_service(session, graph)
            yield AssetImportService(
                AssetImportJobRepository(session), assets, storage_wrapper, session, bucket=_BUCKET
            )

    return _build


def _export_service_factory(
    session_factory: async_sessionmaker[AsyncSession], storage_wrapper: StorageWrapper
) -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[AssetExportService]:
        async with session_scope(session_factory) as session:
            yield AssetExportService(
                AssetExportJobRepository(session),
                AssetRepository(session),
                AssetTagRepository(session),
                storage_wrapper,
                session,
                bucket=_BUCKET,
            )

    return _build


async def test_create_job_commits_before_returning(
    real_session_factory: RealSessionFactory,
    storage_wrapper: StorageWrapper,
    real_neo4j_driver: AsyncDriver,
) -> None:
    """Immediately after ``create_job()`` returns -- before any worker
    ever touches the row -- an independent session must already see it.
    This is exactly the window between ``create_job()`` returning and
    ``producer.publish()`` firing in the real HTTP handler.
    """
    factory, created_job_ids, _created_asset_ids = real_session_factory
    graph = TopologyGraphClient(real_neo4j_driver)
    factory_cm = _import_service_factory(factory, storage_wrapper, graph)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            organization_id=uuid.uuid4(),
            source_format=ImportFormat.JSON,
            filename="a.json",
            content=b"[]",
            preview_only=True,
        )
    created_job_ids.append(job.id)

    async with factory() as independent_session:
        found = await AssetImportJobRepository(independent_session).get_by_id(job.id)
    assert found is not None
    assert found.id == job.id


async def test_export_create_job_commits_before_returning(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    factory, created_job_ids, _created_asset_ids = real_session_factory
    factory_cm = _export_service_factory(factory, storage_wrapper)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            organization_id=uuid.uuid4(),
            target_format=ExportFormat.JSON,
            filter_criteria={},
        )
    created_job_ids.append(job.id)

    async with factory() as independent_session:
        found = await AssetExportJobRepository(independent_session).get_by_id(job.id)
    assert found is not None


async def test_import_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory,
    storage_wrapper: StorageWrapper,
    real_neo4j_driver: AsyncDriver,
) -> None:
    """The worker handler must leave the job ``COMPLETED`` in a way a
    *separate* session/connection can see, not just the session the
    worker happened to run on.
    """
    factory, created_job_ids, created_asset_ids = real_session_factory
    graph = TopologyGraphClient(real_neo4j_driver)
    factory_cm = _import_service_factory(factory, storage_wrapper, graph)

    org_id = uuid.uuid4()
    content = b'[{"name": "worker-regression", "asset_type": "database"}]'
    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            organization_id=org_id,
            source_format=ImportFormat.JSON,
            filename="a.json",
            content=content,
            preview_only=False,
        )
    created_job_ids.append(job.id)

    handler = build_import_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await AssetImportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.succeeded_rows == 1
        created_asset_ids.extend(uuid.UUID(raw) for raw in completed.created_asset_ids)
        created = await AssetRepository(verify_session).get_by_hostname(org_id, "n/a")
        assert created is None  # no hostname was set -- just confirms no crash on lookup


async def test_export_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    factory, created_job_ids, created_asset_ids = real_session_factory
    factory_cm = _export_service_factory(factory, storage_wrapper)
    org_id = uuid.uuid4()

    async with session_scope(factory) as setup_session:
        asset = Asset(
            organization_id=org_id,
            name="export-regression",
            asset_type=AssetType.DATABASE,
            current_version=1,
        )
        await AssetRepository(setup_session).create(asset)
    created_asset_ids.append(asset.id)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            organization_id=org_id,
            target_format=ExportFormat.JSON,
            filter_criteria={},
        )
    created_job_ids.append(job.id)

    handler = build_export_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await AssetExportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.result_storage_key is not None


def _always_failing_import_factory() -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[AssetImportService]:
        service = AsyncMock(spec=AssetImportService)
        service.process_job.side_effect = RuntimeError("boom")
        yield service

    return _build


def _always_failing_export_factory() -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[AssetExportService]:
        service = AsyncMock(spec=AssetExportService)
        service.process_job.side_effect = RuntimeError("boom")
        yield service

    return _build


async def test_import_worker_reraises_on_processing_failure() -> None:
    """The worker logs and re-raises rather than swallowing a failed job --
    a job that errors must not be silently acknowledged as done.
    """
    handler = build_import_worker(_always_failing_import_factory())

    with pytest.raises(RuntimeError, match="boom"):
        await handler({"job_id": str(uuid.uuid4())})


async def test_export_worker_reraises_on_processing_failure() -> None:
    handler = build_export_worker(_always_failing_export_factory())

    with pytest.raises(RuntimeError, match="boom"):
        await handler({"job_id": str(uuid.uuid4())})


__all__: list[str] = []
