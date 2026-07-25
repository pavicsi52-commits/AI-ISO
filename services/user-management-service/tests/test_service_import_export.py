"""Tests for :class:`app.services.import_service.UserImportService` and
:class:`app.services.export_service.UserExportService`, against real
Postgres and MinIO.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.notifications.manager import NotificationManager
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ExportFormat, ImportFormat
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.parsers.excel_parser import write_excel_rows
from app.repositories.activity import UserActivityRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.export_service import UserExportService
from app.services.import_service import UserImportService
from app.services.user import UserService

_BUCKET = "test-import-export"


async def _make_user(session: AsyncSession) -> User:
    return await UserRepository(session).create(
        User(
            username=f"user-{uuid.uuid4().hex[:12]}",
            email=f"user-{uuid.uuid4().hex}@example.com",
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )


def _import_service(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> UserImportService:
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


async def test_import_csv_creates_users(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = b"username,email\nimp1,imp1@example.com\nimp2,imp2@example.com\n"
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.status == JobStatus.COMPLETED
    assert completed.total_rows == 2
    assert completed.succeeded_rows == 2
    assert len(completed.created_user_ids) == 2


async def test_import_json_creates_users(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    json_content = b'[{"username": "jsonimp1", "email": "jsonimp1@example.com"}]'
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=json_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.succeeded_rows == 1


async def test_import_excel_creates_users(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    excel_content = write_excel_rows(
        [{"username": "xlimp1", "email": "xlimp1@example.com"}], ["username", "email"]
    )
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.EXCEL,
        filename="a.xlsx",
        content=excel_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.succeeded_rows == 1


async def test_import_preview_only_does_not_create_users(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = b"username,email\npreview1,preview1@example.com\n"
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=True,
    )

    completed = await service.process_job(job.id)

    assert completed.succeeded_rows == 1
    assert completed.created_user_ids == []
    assert await UserRepository(db_session).get_by_username("preview1") is None


async def test_import_reports_missing_required_fields(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = b"username,email\n,missingusername@example.com\n"
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.failed_rows == 1
    assert len(completed.error_report) == 1


async def test_import_detects_duplicate_within_file(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = b"username,email\ndup1,dup1@example.com\ndup1,dup1-again@example.com\n"
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.succeeded_rows == 1
    assert completed.duplicate_rows == 1


async def test_import_reports_conflict_with_existing_user(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    existing = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = f"username,email\n{existing.username},new-email@example.com\n".encode()
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=False,
    )

    completed = await service.process_job(job.id)

    assert completed.failed_rows == 1


async def test_process_job_rejects_already_processed(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=b"username,email\n",
        preview_only=False,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.process_job(job.id)


async def test_rollback_removes_created_users(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    csv_content = b"username,email\nrollback1,rollback1@example.com\n"
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=csv_content,
        preview_only=False,
    )
    await service.process_job(job.id)

    rolled_back = await service.rollback_job(job.id)

    assert rolled_back.rolled_back_at is not None
    assert await UserRepository(db_session).get_by_username("rollback1") is None


async def test_rollback_rejects_preview_only_job(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=b"username,email\npreviewonly,previewonly@example.com\n",
        preview_only=True,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.rollback_job(job.id)


async def test_get_job_returns_job(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id,
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=b"username,email\n",
        preview_only=False,
    )

    found = await service.get_job(job.id)

    assert found.id == job.id


# --- Export ---


async def test_export_csv_produces_downloadable_file(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(requester.id, target_format=ExportFormat.CSV, filter_criteria={})

    completed = await service.process_job(job.id)

    assert completed.status == JobStatus.COMPLETED
    assert completed.total_rows >= 2
    assert completed.result_storage_key is not None
    url = await service.download_url(completed)
    assert url is not None


async def test_export_pdf_produces_downloadable_file(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(requester.id, target_format=ExportFormat.PDF, filter_criteria={})

    completed = await service.process_job(job.id)

    assert completed.result_storage_key is not None


async def test_export_with_status_filter(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id, target_format=ExportFormat.JSON, filter_criteria={"status": "pending"}
    )

    completed = await service.process_job(job.id)

    assert completed.status == JobStatus.COMPLETED


async def test_export_process_job_rejects_already_processed(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id, target_format=ExportFormat.JSON, filter_criteria={}
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.process_job(job.id)


async def test_download_url_none_before_completion(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id, target_format=ExportFormat.JSON, filter_criteria={}
    )

    assert await service.download_url(job) is None


async def test_export_get_job_returns_job(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    requester = await _make_user(db_session)
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        requester.id, target_format=ExportFormat.JSON, filter_criteria={}
    )

    found = await service.get_job(job.id)

    assert found.id == job.id
