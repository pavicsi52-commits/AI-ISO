"""Direct service-layer tests for ``app/services/import_service.py``/
``app/services/export_service.py``: parsing, validation, conflict
detection, preview, rollback, and every supported format. Uses the
test's own SAVEPOINT-scoped ``db_session`` directly -- ``create_job()``'s
own ``commit()`` just releases the savepoint on such a session (see
``test_worker_regression.py`` for the dedicated cross-connection proof
that this genuinely commits on a real session), so a plain, simpler
same-session round trip works fine here.
"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExportFormat, ImportFormat, ProjectStatus
from app.models.project_tag import ProjectTag
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
from tests.conftest import make_project

_BUCKET = "project-import-export-test"


def _import_service(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> ProjectImportService:
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


async def test_import_json_creates_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    requester = uuid.uuid4()
    content = f'[{{"organization_id": "{org_id}", "name": "A", "code": "svc-imp-a"}}]'.encode()
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        requester,
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.succeeded_rows == 1
    assert len(result.created_project_ids) == 1
    created = await ProjectRepository(db_session).get_by_code(org_id, "svc-imp-a")
    assert created is not None


async def test_import_yaml_creates_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    content = (
        f"- organization_id: '{org_id}'\n  name: YAML Project\n  code: svc-imp-yaml\n".encode()
    )
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.YAML,
        filename="a.yaml",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1


async def test_import_csv_creates_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    content = f"organization_id,name,code\n{org_id},CSV Project,svc-imp-csv\n".encode()
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1


async def test_import_zip_extracts_and_creates_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    inner = f'[{{"organization_id": "{org_id}", "name": "Zipped", "code": "svc-imp-zip"}}]'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.json", inner)
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.ZIP,
        filename="a.zip",
        content=buffer.getvalue(),
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1


async def test_import_preview_only_does_not_create_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Preview", '
        '"code": "svc-imp-preview"}]'.encode()
    )
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=True,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1
    assert result.created_project_ids == []
    assert await ProjectRepository(db_session).get_by_code(org_id, "svc-imp-preview") is None


async def test_import_missing_required_field_reports_error(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    content = b'[{"name": "No Org Or Code"}]'
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.failed_rows == 1
    assert result.succeeded_rows == 0
    assert "Missing required fields" in result.error_report[0]["error"]


async def test_import_duplicate_code_within_file_reports_duplicate(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "First", "code": "svc-imp-dup"}}, '
        f'{{"organization_id": "{org_id}", "name": "Second", "code": "svc-imp-dup"}}]'
    ).encode()
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1
    assert result.duplicate_rows == 1


async def test_import_conflicting_existing_code_reports_failure(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id, code="svc-imp-existing")
    content = (
        f'[{{"organization_id": "{org_id}", "name": "Dup", "code": "svc-imp-existing"}}]'.encode()
    )
    service = _import_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.failed_rows == 1
    assert result.succeeded_rows == 0


async def test_import_invalid_json_fails_job(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"not json",
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.FAILED
    assert result.error_report


async def test_process_job_twice_conflicts(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=False,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.process_job(job.id)


async def test_rollback_deletes_created_projects(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    content = (
        f'[{{"organization_id": "{org_id}", "name": "ToRollback", "code": "svc-imp-rb"}}]'.encode()
    )
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    await service.process_job(job.id)

    rolled_back = await service.rollback_job(job.id)

    assert rolled_back.rolled_back_at is not None
    project = await ProjectRepository(db_session).get_by_id(
        uuid.UUID(rolled_back.created_project_ids[0]), include_deleted=True
    )
    assert project is not None
    assert project.is_active is False


async def test_rollback_preview_only_job_conflicts(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _import_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=True,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.rollback_job(job.id)


# --- Export ---


async def test_export_json(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id, name="Exportable")
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={"organization_id": str(org_id)},
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.total_rows == 1
    assert result.result_storage_key is not None


async def test_export_yaml(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id)
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.YAML,
        filter_criteria={"organization_id": str(org_id)},
    )
    result = await service.process_job(job.id)

    assert result.result_storage_key is not None
    assert result.result_storage_key.endswith(".yaml")


async def test_export_pdf(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id)
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.PDF,
        filter_criteria={"organization_id": str(org_id)},
    )
    result = await service.process_job(job.id)

    assert result.result_storage_key is not None
    assert result.result_storage_key.endswith(".pdf")


async def test_export_zip_package(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id)
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.ZIP,
        filter_criteria={"organization_id": str(org_id)},
    )
    result = await service.process_job(job.id)

    assert result.result_storage_key is not None
    assert result.result_storage_key.endswith(".zip")


async def test_export_filters_by_status_and_category(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    await make_project(db_session, organization_id=org_id, status=ProjectStatus.ACTIVE)
    await make_project(db_session, organization_id=org_id, status=ProjectStatus.DRAFT)
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={"organization_id": str(org_id), "status": "active"},
    )
    result = await service.process_job(job.id)

    assert result.total_rows == 1


async def test_export_filters_by_tags(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    tagged = await make_project(db_session, organization_id=org_id, name="Tagged")
    await make_project(db_session, organization_id=org_id, name="Untagged")
    db_session.add(ProjectTag(project_id=tagged.id, organization_id=org_id, label="critical"))
    await db_session.flush()
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={"organization_id": str(org_id), "tags": ["critical"]},
    )
    result = await service.process_job(job.id)

    assert result.total_rows == 1


async def test_get_job_not_found(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> None:
    import_service = _import_service(db_session, storage_wrapper)
    export_service = _export_service(db_session, storage_wrapper)

    with pytest.raises(NotFoundError):
        await import_service.get_job(uuid.uuid4())
    with pytest.raises(NotFoundError):
        await export_service.get_job(uuid.uuid4())


async def test_export_process_job_twice_conflicts(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={"organization_id": str(org_id)},
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.process_job(job.id)


async def test_download_url_none_when_not_completed(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={"organization_id": str(org_id)},
    )

    assert await service.download_url(job) is None
