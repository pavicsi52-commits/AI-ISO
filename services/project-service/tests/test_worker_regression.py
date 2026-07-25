"""Regression tests for two commit-visibility bugs found via live
smoke-testing.

**Bug 1 (this service's own, found first)**: ``ProjectImportService
.create_job()``/``ProjectExportService.create_job()`` used to rely on
the *request's* ``session_scope`` dependency teardown to commit the new
job row -- but the HTTP handler calls ``producer.publish()``
*immediately* after ``create_job()`` returns, well before that
teardown runs. A same-process RabbitMQ round trip can be fast enough
that the in-process worker's ``require_by_id()`` call arrives before
the commit, producing a real, deterministic (reproduced on the very
first live test) ``NotFoundError`` -- not a rare race. The fix makes
``create_job()`` commit immediately, before returning to the router.

**Bug 2 (the shape every prior AI-IOS service's own import/export
worker already caught)**: a background job processed through a bare
``session_factory()`` call only *flushes* its changes and never
durably commits them, so an independent session polling the job's
status sees it stuck forever even after the worker itself finished.
The fix wraps the worker's own service factories in
:func:`shared_core.database.session.session_scope` (see
``app/core/factory.py``'s ``_build_import_service``/
``_build_export_service``).

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
from shared_core.database.session import session_scope
from shared_core.enums.job_status import JobStatus
from shared_core.storage import StorageWrapper
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.enums import ExportFormat, ImportFormat
from app.models.project import Project
from app.models.project_export_job import ProjectExportJob
from app.models.project_import_job import ProjectImportJob
from app.repositories.project import ProjectRepository
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_archive import ProjectArchiveRepository
from app.repositories.project_export_job import ProjectExportJobRepository
from app.repositories.project_import_job import ProjectImportJobRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.repositories.project_tag import ProjectTagRepository
from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService
from app.services.export_service import ProjectExportService
from app.services.import_service import ProjectImportService
from app.services.project import ProjectService
from app.workers.export_worker import ExportServiceFactory, build_export_worker
from app.workers.import_worker import ImportServiceFactory, build_import_worker

_BUCKET = "project-import-export-test"

RealSessionFactory = tuple[async_sessionmaker[AsyncSession], list[uuid.UUID], list[uuid.UUID]]
"""``(session_factory, created_project_ids, created_job_ids)`` -- the
latter two are mutated by tests so the fixture's own teardown can clean
them up.
"""


@pytest_asyncio.fixture
async def real_session_factory(pg_engine: AsyncEngine) -> AsyncIterator[RealSessionFactory]:
    """A plain session factory bound directly to the engine -- i.e.
    exactly what ``create_database_framework`` hands the real app as
    ``database.session_factory``, with no SAVEPOINT/rollback safety net.
    Every row this test creates is cleaned up explicitly in teardown.
    """
    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    created_project_ids: list[uuid.UUID] = []
    created_job_ids: list[uuid.UUID] = []
    yield factory, created_project_ids, created_job_ids
    async with factory() as cleanup_session:
        if created_job_ids:
            await cleanup_session.execute(
                delete(ProjectImportJob).where(ProjectImportJob.id.in_(created_job_ids))
            )
            await cleanup_session.execute(
                delete(ProjectExportJob).where(ProjectExportJob.id.in_(created_job_ids))
            )
        if created_project_ids:
            await cleanup_session.execute(
                delete(Project).where(Project.id.in_(created_project_ids))
            )
        await cleanup_session.commit()


def _import_service_factory(
    session_factory: async_sessionmaker[AsyncSession], storage_wrapper: StorageWrapper
) -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[ProjectImportService]:
        async with session_scope(session_factory) as session:
            activity = ProjectActivityService(ProjectActivityRepository(session))
            archives = ProjectArchiveService(ProjectArchiveRepository(session))
            projects = ProjectService(
                ProjectRepository(session),
                ProjectSettingsRepository(session),
                ProjectPreferencesRepository(session),
                activity,
                archives,
                publish_event=None,
            )
            yield ProjectImportService(
                ProjectImportJobRepository(session),
                projects,
                storage_wrapper,
                session,
                bucket=_BUCKET,
            )

    return _build


def _export_service_factory(
    session_factory: async_sessionmaker[AsyncSession], storage_wrapper: StorageWrapper
) -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[ProjectExportService]:
        async with session_scope(session_factory) as session:
            yield ProjectExportService(
                ProjectExportJobRepository(session),
                ProjectRepository(session),
                ProjectTagRepository(session),
                storage_wrapper,
                session,
                bucket=_BUCKET,
            )

    return _build


async def test_create_job_commits_before_returning(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """Bug 1's actual regression test: immediately after ``create_job()``
    returns -- *before* any worker ever touches the row -- an
    independent session must already see it. This is exactly the window
    between ``create_job()`` returning and ``producer.publish()`` firing
    in the real HTTP handler.
    """
    factory, _created_project_ids, created_job_ids = real_session_factory
    factory_cm = _import_service_factory(factory, storage_wrapper)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            source_format=ImportFormat.JSON,
            filename="a.json",
            content=b"[]",
            preview_only=True,
        )
    created_job_ids.append(job.id)

    async with factory() as independent_session:
        found = await ProjectImportJobRepository(independent_session).get_by_id(job.id)
    assert found is not None
    assert found.id == job.id


async def test_export_create_job_commits_before_returning(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """The export side of the same Bug 1 regression."""
    factory, _created_project_ids, created_job_ids = real_session_factory
    factory_cm = _export_service_factory(factory, storage_wrapper)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            target_format=ExportFormat.JSON,
            filter_criteria={"organization_id": str(uuid.uuid4())},
        )
    created_job_ids.append(job.id)

    async with factory() as independent_session:
        found = await ProjectExportJobRepository(independent_session).get_by_id(job.id)
    assert found is not None


async def test_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """Bug 2's regression test: the worker handler must leave the job
    ``COMPLETED`` in a way a *separate* session/connection can see, not
    just the session the worker happened to run on.
    """
    factory, created_project_ids, created_job_ids = real_session_factory
    factory_cm = _import_service_factory(factory, storage_wrapper)

    requester = uuid.uuid4()
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Worker Regression", "code": "wrk-reg-1"}}]'
    )
    async with factory_cm() as create_service:
        job = await create_service.create_job(
            requester,
            source_format=ImportFormat.JSON,
            filename="a.json",
            content=content.encode(),
            preview_only=False,
        )
    created_job_ids.append(job.id)

    handler = build_import_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await ProjectImportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.succeeded_rows == 1
        created = await ProjectRepository(verify_session).get_by_code(org_id, "wrk-reg-1")
        assert created is not None
        created_project_ids.append(created.id)


async def test_export_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """The export side of the same Bug 2 regression."""
    factory, created_project_ids, created_job_ids = real_session_factory
    factory_cm = _export_service_factory(factory, storage_wrapper)
    org_id = uuid.uuid4()

    async with session_scope(factory) as setup_session:
        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            project_id=project_id,
            organization_id=org_id,
            name="Export Regression",
            code="exp-reg-1",
            owner_id=uuid.uuid4(),
        )
        await ProjectRepository(setup_session).create(project)
    created_project_ids.append(project_id)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            uuid.uuid4(),
            target_format=ExportFormat.JSON,
            filter_criteria={"organization_id": str(org_id)},
        )
    created_job_ids.append(job.id)

    handler = build_export_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await ProjectExportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.result_storage_key is not None


def _always_failing_import_factory() -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[ProjectImportService]:
        service = AsyncMock(spec=ProjectImportService)
        service.process_job.side_effect = RuntimeError("boom")
        yield service

    return _build


def _always_failing_export_factory() -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[ProjectExportService]:
        service = AsyncMock(spec=ProjectExportService)
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
