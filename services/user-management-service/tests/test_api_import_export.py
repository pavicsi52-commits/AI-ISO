"""HTTP-level tests for POST/GET /users/import and /users/export.

The real app lifespan wires a real RabbitMQ producer/consumer (see
``app/core/factory.py``) that reads/writes through the *process-wide*
session factory, not this test's SAVEPOINT-isolated session -- so a job
queued for real would never actually get processed within a test (the
consumer's own transaction can't see this test's uncommitted rows), and
worse, its stray background task can race the test's own teardown and
disposal of the very engine it's using, producing flaky
``ResourceWarning``s. ``get_queue_producer`` is therefore stubbed out
here so these tests never publish a real message -- the real
publish/consume/worker-commit path is covered by
``test_worker_regression.py`` (direct handler invocation) and was
additionally verified live via curl smoke-testing (see the package
README). Completion is simulated the same way ``test_api_invitation.py``
simulates the emailed token: build a service that shares the test's
``db_session`` directly and call ``process_job()`` on it, standing in
for what the worker would do once it *does* see the row for real.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.export_service import UserExportService
from app.services.import_service import UserImportService
from app.services.user import UserService


@pytest_asyncio.fixture(autouse=True)
async def _stub_queue_producer(app: FastAPI) -> AsyncIterator[None]:
    """Replace the real queue producer with a no-op double for every
    test in this file -- see the module docstring for why.
    """
    app.dependency_overrides[deps.get_queue_producer] = lambda: AsyncMock(spec=Producer)
    yield
    del app.dependency_overrides[deps.get_queue_producer]


_BUCKET = "user-import-export"
"""Matches ``Settings.service.import_export_bucket``'s default -- the
real HTTP router uploads under this bucket, so the service instances
built in this file (standing in for the background worker) must read
from the same one.
"""


async def _create_caller(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> tuple[uuid.UUID, dict[str, str]]:
    admin_headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/users",
        headers=admin_headers,
        json={
            "username": f"user-{uuid.uuid4().hex[:12]}",
            "email": f"user-{uuid.uuid4().hex}@example.com",
        },
    )
    assert response.status_code == 201, response.text
    user_id = uuid.UUID(response.json()["data"]["id"])
    return user_id, auth_headers(user_id)


def _import_service(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> UserImportService:
    """Build a :class:`UserImportService` on the same session ``client``'s
    requests share, so a job created over HTTP is visible here too --
    standing in for what the real background worker does once it can see
    the row through its own (real) session.
    """
    activity = UserActivityService(UserActivityRepository(db_session))
    notifications = UserNotificationService(AsyncMock(spec=NotificationManager))
    users = UserService(UserRepository(db_session), activity, notifications)
    return UserImportService(
        UserImportJobRepository(db_session), users, activity, storage_wrapper, bucket=_BUCKET
    )


def _export_service(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> UserExportService:
    activity = UserActivityService(UserActivityRepository(db_session))
    return UserExportService(
        UserExportJobRepository(db_session),
        UserRepository(db_session),
        activity,
        storage_wrapper,
        bucket=_BUCKET,
    )


# --- Import ---


async def test_start_import_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    csv_content = b"username,email\nhttpimp1,httpimp1@example.com\n"

    response = await client.post(
        "/users/import",
        headers=headers,
        files={"file": ("users.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"


async def test_import_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/users/import", files={"file": ("users.csv", b"username,email\n", "text/csv")}
    )

    assert response.status_code == 401


async def test_get_import_job_reflects_processing(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    csv_content = b"username,email\nhttpimp2,httpimp2@example.com\n"
    started = await client.post(
        "/users/import",
        headers=headers,
        files={"file": ("users.csv", csv_content, "text/csv")},
    )
    job_id = started.json()["data"]["job_id"]

    await _import_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.get(f"/users/import/{job_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["succeeded_rows"] == 1


async def test_rollback_import_job(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    csv_content = b"username,email\nhttprollback1,httprollback1@example.com\n"
    started = await client.post(
        "/users/import",
        headers=headers,
        files={"file": ("users.csv", csv_content, "text/csv")},
    )
    job_id = started.json()["data"]["job_id"]
    await _import_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.post(f"/users/import/{job_id}/rollback", headers=headers)

    assert response.status_code == 200
    assert await UserRepository(db_session).get_by_username("httprollback1") is None


# --- Export ---


async def test_start_export_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)

    response = await client.post("/users/export", headers=headers, json={"target_format": "csv"})

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"
    assert response.json()["data"]["download_url"] is None


async def test_export_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/users/export", json={"target_format": "csv"})

    assert response.status_code == 401


async def test_get_export_job_reflects_processing_and_download_url(
    client: AsyncClient,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
) -> None:
    _user_id, headers = await _create_caller(client, auth_headers)
    started = await client.post("/users/export", headers=headers, json={"target_format": "json"})
    job_id = started.json()["data"]["job_id"]

    await _export_service(db_session, storage_wrapper).process_job(uuid.UUID(job_id))

    response = await client.get(f"/users/export/{job_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["download_url"] is not None
