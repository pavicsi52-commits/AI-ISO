"""Regression test for the worker session-commit bug found via live
smoke-testing: a background job processed through a bare
``session_factory()`` call only *flushed* its changes (visible to its
own session) and never durably ``COMMIT``ted them, so a client polling
``GET /users/import/{job_id}`` on its own, independently connected
session saw the job stuck at "queued" forever, even though the worker
itself had already finished successfully.

The fix wraps the worker's service factories in
:func:`shared_core.database.session.session_scope` (see
``app/core/factory.py``'s ``_build_import_service``/
``_build_export_service``). Proving this needs two genuinely
independent connections -- the test's usual ``db_session`` fixture is a
single SAVEPOINT inside one never-committed outer transaction, which
can't demonstrate cross-connection visibility -- so this file builds
its own plain (non-SAVEPOINT) session factory directly on ``pg_engine``
and cleans up everything it writes.
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
from shared_core.notifications.manager import NotificationManager
from shared_core.storage import StorageWrapper
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.activity import UserActivityEntry
from app.models.enums import ExportFormat, ImportFormat
from app.models.export_job import UserExportJob
from app.models.import_job import UserImportJob
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.export_service import UserExportService
from app.services.import_service import UserImportService
from app.services.user import UserService
from app.workers.export_worker import ExportServiceFactory, build_export_worker
from app.workers.import_worker import ImportServiceFactory, build_import_worker

_BUCKET = "user-import-export"

RealSessionFactory = tuple[async_sessionmaker[AsyncSession], list[uuid.UUID], list[uuid.UUID]]
"""``(session_factory, created_user_ids, created_job_ids)`` -- the latter
two are mutated by tests so the fixture's own teardown can clean them up.
"""


@pytest_asyncio.fixture
async def real_session_factory(pg_engine: AsyncEngine) -> AsyncIterator[RealSessionFactory]:
    """A plain session factory bound directly to the engine -- i.e.
    exactly what ``create_database_framework`` hands the real app as
    ``database.session_factory``, with no SAVEPOINT/rollback safety net.
    Every row this test creates is cleaned up explicitly in teardown.
    """
    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)
    created_user_ids: list[uuid.UUID] = []
    created_job_ids: list[uuid.UUID] = []
    yield factory, created_user_ids, created_job_ids
    async with factory() as cleanup_session:
        if created_job_ids:
            await cleanup_session.execute(
                delete(UserImportJob).where(UserImportJob.id.in_(created_job_ids))
            )
            await cleanup_session.execute(
                delete(UserExportJob).where(UserExportJob.id.in_(created_job_ids))
            )
        if created_user_ids:
            # UserService.create()/InvitationService etc. record UserActivityEntry
            # rows with a real FK to users.id -- those must go first, or the
            # user DELETE below violates that constraint.
            await cleanup_session.execute(
                delete(UserActivityEntry).where(UserActivityEntry.user_id.in_(created_user_ids))
            )
            await cleanup_session.execute(delete(User).where(User.id.in_(created_user_ids)))
        await cleanup_session.commit()


def _service_factory(
    session_factory: async_sessionmaker[AsyncSession], storage_wrapper: StorageWrapper
) -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[UserImportService]:
        async with session_scope(session_factory) as session:
            activity = UserActivityService(UserActivityRepository(session))
            notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
            users = UserService(UserRepository(session), activity, notifications)
            yield UserImportService(
                UserImportJobRepository(session), users, activity, storage_wrapper, bucket=_BUCKET
            )

    return _build


def _export_service_factory(
    session_factory: async_sessionmaker[AsyncSession], storage_wrapper: StorageWrapper
) -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[UserExportService]:
        async with session_scope(session_factory) as session:
            activity = UserActivityService(UserActivityRepository(session))
            yield UserExportService(
                UserExportJobRepository(session),
                UserRepository(session),
                activity,
                storage_wrapper,
                bucket=_BUCKET,
            )

    return _build


async def test_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """The regression itself: the worker handler must leave the job
    ``COMPLETED`` in a way a *separate* session/connection can see, not
    just the session the worker happened to run on.
    """
    factory, created_user_ids, created_job_ids = real_session_factory
    factory_cm = _service_factory(factory, storage_wrapper)

    async with session_scope(factory) as setup_session:
        requester = await UserRepository(setup_session).create(
            User(
                username=f"worker-req-{uuid.uuid4().hex[:12]}",
                email=f"worker-req-{uuid.uuid4().hex}@example.com",
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        created_user_ids.append(requester.id)

    csv_content = b"username,email\nworkerimp1,workerimp1@example.com\n"
    async with factory_cm() as create_service:
        job = await create_service.create_job(
            requester.id,
            source_format=ImportFormat.CSV,
            filename="a.csv",
            content=csv_content,
            preview_only=False,
        )
    created_job_ids.append(job.id)

    handler = build_import_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await UserImportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.succeeded_rows == 1
        created_user = await UserRepository(verify_session).get_by_username("workerimp1")
        assert created_user is not None
        created_user_ids.append(created_user.id)


async def test_flush_only_session_is_not_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory,
) -> None:
    """Documents *why* the fix was needed: a session that only
    ``flush()``es (the pre-fix behavior of a bare ``session_factory()``
    call, since every ``BaseRepository`` write is flush-only by design --
    the Unit-of-Work owns the commit boundary) leaves its changes
    invisible to any other session, even after the writing session has
    finished using them. If this assertion ever starts failing, the
    session-commit bug's root cause has changed and
    ``_build_import_service``/``_build_export_service`` need re-auditing.
    """
    factory, created_user_ids, _created_job_ids = real_session_factory

    async with factory() as flush_only_session:
        user = User(
            username=f"flush-only-{uuid.uuid4().hex[:12]}",
            email=f"flush-only-{uuid.uuid4().hex}@example.com",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
        await UserRepository(flush_only_session).create(user)
        created_user_ids.append(user.id)
        # Deliberately no commit() here -- this is the bug, reproduced.

    async with factory() as independent_session:
        found = await UserRepository(independent_session).get_by_username(user.username)

    assert found is None


async def test_export_worker_commits_are_visible_to_an_independent_session(
    real_session_factory: RealSessionFactory, storage_wrapper: StorageWrapper
) -> None:
    """The export side of the same regression -- see
    ``test_worker_commits_are_visible_to_an_independent_session``.
    """
    factory, created_user_ids, created_job_ids = real_session_factory
    factory_cm = _export_service_factory(factory, storage_wrapper)

    async with session_scope(factory) as setup_session:
        requester = await UserRepository(setup_session).create(
            User(
                username=f"worker-exp-req-{uuid.uuid4().hex[:12]}",
                email=f"worker-exp-req-{uuid.uuid4().hex}@example.com",
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        created_user_ids.append(requester.id)

    async with factory_cm() as create_service:
        job = await create_service.create_job(
            requester.id, target_format=ExportFormat.JSON, filter_criteria={}
        )
    created_job_ids.append(job.id)

    handler = build_export_worker(factory_cm)
    await handler({"job_id": str(job.id)})

    async with factory() as verify_session:
        completed = await UserExportJobRepository(verify_session).require_by_id(job.id)
        assert str(completed.status) == str(JobStatus.COMPLETED)
        assert completed.result_storage_key is not None


def _always_failing_import_factory() -> ImportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[UserImportService]:
        service = AsyncMock(spec=UserImportService)
        service.process_job.side_effect = RuntimeError("boom")
        yield service

    return _build


def _always_failing_export_factory() -> ExportServiceFactory:
    @asynccontextmanager
    async def _build() -> AsyncIterator[UserExportService]:
        service = AsyncMock(spec=UserExportService)
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
