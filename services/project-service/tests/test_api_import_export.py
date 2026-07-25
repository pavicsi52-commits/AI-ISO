"""HTTP-level tests for ``POST/GET /projects/import`` and ``/projects/export``.

The real app lifespan wires a real RabbitMQ producer/consumer (see
``app/core/factory.py``) that reads/writes through the *process-wide*
session factory, not this test's SAVEPOINT-isolated session -- so a job
queued for real would never actually get processed within a test (the
consumer's own transaction can't see this test's uncommitted rows), and
worse, its stray background task can race the test's own teardown.
``get_queue_producer`` is therefore stubbed out here so these tests
never publish a real message -- the real publish/consume/worker-commit
path was verified live via curl smoke-testing (see the package
README). Completion is simulated the same way
``services/user-management-service/tests/test_api_import_export.py``
does: build a service that shares the test's ``db_session`` directly
and call ``process_job()`` on it, standing in for what the worker would
do once it *does* see the row for real.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from shared_core.queue.producer import Producer
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
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
from tests.conftest import make_project_with_owner

_BUCKET = "project-import-export-test"
"""Matches ``AIIOS_PROJECT_SERVICE_IMPORT_EXPORT_BUCKET`` set in
``conftest.py`` -- the real HTTP router uploads under this bucket, so
the service instances built in this file (standing in for the
background worker) must read from the same one.
"""


@pytest_asyncio.fixture(autouse=True)
async def _stub_queue_producer(app: FastAPI) -> AsyncIterator[None]:
    """Replace the real queue producer with a no-op double for every
    test in this file -- see the module docstring for why.
    """
    app.dependency_overrides[deps.get_queue_producer] = lambda: AsyncMock(spec=Producer)
    yield
    del app.dependency_overrides[deps.get_queue_producer]


def _import_service(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> ProjectImportService:
    """Build a :class:`ProjectImportService` on the same session ``client``'s
    requests share, so a job created over HTTP is visible here too --
    standing in for what the real background worker does once it can see
    the row through its own (real) session.
    """
    activity = ProjectActivityService(ProjectActivityRepository(db_session))
    archives = ProjectArchiveService(ProjectArchiveRepository(db_session))
    projects = ProjectService(
        ProjectRepository(db_session),
        ProjectSettingsRepository(db_session),
        ProjectPreferencesRepository(db_session),
        activity,
        archives,
        publish_event=None,
    )
    return ProjectImportService(
        ProjectImportJobRepository(db_session),
        projects,
        storage_wrapper,
        db_session,
        bucket=_BUCKET,
    )


def _export_service(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> ProjectExportService:
    return ProjectExportService(
        ProjectExportJobRepository(db_session),
        ProjectRepository(db_session),
        ProjectTagRepository(db_session),
        storage_wrapper,
        db_session,
        bucket=_BUCKET,
    )


# --- Import ---


async def test_start_import_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Http Import", "code": "http-imp-1"}}]'.encode()
    )

    response = await client.post(
        "/projects/import?source_format=json",
        headers=auth_headers(caller),
        files={"file": ("projects.json", content, "application/json")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"


async def test_import_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/projects/import?source_format=json",
        files={"file": ("projects.json", b"[]", "application/json")},
    )
    assert response.status_code == 401


async def test_get_import_job_reflects_processing(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Http Import 2", '
        '"code": "http-imp-2"}]'.encode()
    )
    started = await client.post(
        "/projects/import?source_format=json",
        headers=auth_headers(caller),
        files={"file": ("projects.json", content, "application/json")},
    )
    job_id = started.json()["data"]["job_id"]

    await _import_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.get(f"/projects/import/{job_id}", headers=auth_headers(caller))
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["succeeded_rows"] == 1


async def test_rollback_import_job(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Http Rollback", '
        '"code": "http-rb-1"}]'.encode()
    )
    started = await client.post(
        "/projects/import?source_format=json",
        headers=auth_headers(caller),
        files={"file": ("projects.json", content, "application/json")},
    )
    job_id = started.json()["data"]["job_id"]
    await _import_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.post(
        f"/projects/import/{job_id}/rollback", headers=auth_headers(caller)
    )

    assert response.status_code == 200
    assert await ProjectRepository(db_session).get_by_code(org_id, "http-rb-1") is None


# --- Export ---


async def test_start_export_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    caller = uuid.uuid4()
    response = await client.post(
        "/projects/export",
        headers=auth_headers(caller),
        json={"organization_id": str(uuid.uuid4()), "target_format": "json"},
    )
    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"
    assert response.json()["data"]["download_url"] is None


async def test_export_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/projects/export", json={"organization_id": str(uuid.uuid4()), "target_format": "json"}
    )
    assert response.status_code == 401


async def test_get_export_job_reflects_processing_and_download_url(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    storage_wrapper: StorageWrapper,
) -> None:
    caller = uuid.uuid4()
    org_id = uuid.uuid4()
    await make_project_with_owner(db_session, caller, organization_id=org_id)

    started = await client.post(
        "/projects/export",
        headers=auth_headers(caller),
        json={"organization_id": str(org_id), "target_format": "json"},
    )
    job_id = started.json()["data"]["job_id"]

    await _export_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.get(f"/projects/export/{job_id}", headers=auth_headers(caller))
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["download_url"] is not None
