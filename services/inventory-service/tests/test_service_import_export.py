"""Direct service-layer tests for ``app/services/import_service.py``/
``app/services/export_service.py``: parsing, validation, duplicate
detection, preview, rollback, and every supported format. Uses the
test's own SAVEPOINT-scoped ``db_session`` directly -- ``create_job()``'s
own ``commit()`` just releases the savepoint on such a session, the same
"a plain, simpler same-session round trip works fine here" rationale
``services/project-service``'s own identical test file documents (its
own ``test_worker_regression.py`` is where the real cross-connection
commit behavior gets proven, mirrored here in ``test_workers.py``).
"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AssetType, ExportFormat, ImportFormat
from app.parsers.excel_parser import write_excel_rows
from app.repositories.asset import AssetRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_tag import AssetTagRepository
from app.services.export_service import AssetExportService
from app.services.import_service import AssetImportService
from app.services.tag import AssetTagService
from app.topology.graph import TopologyGraphClient
from tests.conftest import build_asset_service, make_asset

_BUCKET = "inventory-import-export-test"


def _import_service(
    db_session: AsyncSession, storage_wrapper: StorageWrapper, graph: TopologyGraphClient
) -> AssetImportService:
    assets = build_asset_service(db_session, graph)
    return AssetImportService(
        AssetImportJobRepository(db_session), assets, storage_wrapper, db_session, bucket=_BUCKET
    )


def _export_service(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> AssetExportService:
    return AssetExportService(
        AssetExportJobRepository(db_session),
        AssetRepository(db_session),
        AssetTagRepository(db_session),
        storage_wrapper,
        db_session,
        bucket=_BUCKET,
    )


# --- Import ---


async def test_import_json_creates_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    org_id = uuid.uuid4()
    content = (
        b'[{"name": "web-01", "asset_type": "virtual_machine", "hostname": "web-01.internal"}]'
    )
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=org_id,
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.succeeded_rows == 1
    assert len(result.created_asset_ids) == 1
    created = await AssetRepository(db_session).get_by_hostname(org_id, "web-01.internal")
    assert created is not None


async def test_import_yaml_creates_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = b"- name: yaml-asset\n  asset_type: database\n"
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.YAML,
        filename="a.yaml",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)
    assert result.succeeded_rows == 1


async def test_import_csv_creates_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = b"name,asset_type\ncsv-asset,container\n"
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.CSV,
        filename="a.csv",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)
    assert result.succeeded_rows == 1


async def test_import_excel_creates_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = write_excel_rows(
        [{"name": "excel-asset", "asset_type": "switch"}], ["name", "asset_type"]
    )
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.EXCEL,
        filename="a.xlsx",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)
    assert result.succeeded_rows == 1


async def test_import_zip_extracts_and_creates_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    inner = '[{"name": "zipped-asset", "asset_type": "firewall"}]'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.json", inner)
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.ZIP,
        filename="a.zip",
        content=buffer.getvalue(),
        preview_only=False,
    )
    result = await service.process_job(job.id)
    assert result.succeeded_rows == 1


async def test_import_zip_extracts_yaml_csv_excel(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    for inner_name, inner_content in (
        ("data.yaml", b"- name: yz\n  asset_type: router\n"),
        ("data.csv", b"name,asset_type\ncz,router\n"),
    ):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(inner_name, inner_content)
        job = await service.create_job(
            uuid.uuid4(),
            organization_id=uuid.uuid4(),
            source_format=ImportFormat.ZIP,
            filename="a.zip",
            content=buffer.getvalue(),
            preview_only=False,
        )
        result = await service.process_job(job.id)
        assert result.succeeded_rows == 1


async def test_import_preview_only_does_not_create_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    org_id = uuid.uuid4()
    content = (
        b'[{"name": "preview-asset", "asset_type": "container", "hostname": "preview.internal"}]'
    )
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=org_id,
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=True,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1
    assert result.created_asset_ids == []
    assert await AssetRepository(db_session).get_by_hostname(org_id, "preview.internal") is None


async def test_import_missing_required_field_reports_error(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = b'[{"name": "no-type"}]'
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.failed_rows == 1
    assert result.succeeded_rows == 0
    assert "Missing required fields" in result.error_report[0]["error"]


async def test_import_duplicate_hostname_within_file_reports_duplicate(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = (
        b'[{"name": "first", "asset_type": "physical_server", "hostname": "dup.internal"}, '
        b'{"name": "second", "asset_type": "physical_server", "hostname": "dup.internal"}]'
    )
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.succeeded_rows == 1
    assert result.duplicate_rows == 1


async def test_import_conflicting_existing_hostname_reports_failure(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id, hostname="existing.internal")
    content = b'[{"name": "dup", "asset_type": "physical_server", "hostname": "existing.internal"}]'
    service = _import_service(db_session, storage_wrapper, topology_graph_client)

    job = await service.create_job(
        uuid.uuid4(),
        organization_id=org_id,
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.failed_rows == 1
    assert result.succeeded_rows == 0


async def test_import_invalid_json_fails_job(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"not json",
        preview_only=False,
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.FAILED
    assert result.error_report


async def test_process_job_twice_conflicts(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=False,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.process_job(job.id)


async def test_rollback_deletes_created_assets(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    content = (
        b'[{"name": "to-rollback", "asset_type": "physical_server", "hostname": "rb.internal"}]'
    )
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=content,
        preview_only=False,
    )
    await service.process_job(job.id)

    rolled_back = await service.rollback_job(job.id)

    assert rolled_back.rolled_back_at is not None
    asset = await AssetRepository(db_session).get_by_id(
        uuid.UUID(rolled_back.created_asset_ids[0]), include_deleted=True
    )
    assert asset is not None
    assert asset.is_active is False


async def test_rollback_preview_only_job_conflicts(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=True,
    )
    await service.process_job(job.id)

    with pytest.raises(ConflictError):
        await service.rollback_job(job.id)


async def test_rollback_never_processed_job_conflicts(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=False,
    )
    with pytest.raises(ConflictError):
        await service.rollback_job(job.id)


async def test_get_job(
    db_session: AsyncSession,
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    service = _import_service(db_session, storage_wrapper, topology_graph_client)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_format=ImportFormat.JSON,
        filename="a.json",
        content=b"[]",
        preview_only=False,
    )
    fetched = await service.get_job(job.id)
    assert fetched.id == job.id


# --- Export ---


async def test_export_json(db_session: AsyncSession, storage_wrapper: StorageWrapper) -> None:
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id, name="exportable")
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(), organization_id=org_id, target_format=ExportFormat.JSON, filter_criteria={}
    )
    result = await service.process_job(job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.total_rows == 1
    assert result.result_storage_key is not None
    url = await service.download_url(result)
    assert url is not None


@pytest.mark.parametrize(
    "target_format",
    [ExportFormat.YAML, ExportFormat.CSV, ExportFormat.EXCEL, ExportFormat.PDF, ExportFormat.ZIP],
)
async def test_export_every_format(
    db_session: AsyncSession, storage_wrapper: StorageWrapper, target_format: ExportFormat
) -> None:
    org_id = uuid.uuid4()
    await make_asset(db_session, organization_id=org_id, name="exportable")
    service = _export_service(db_session, storage_wrapper)

    job = await service.create_job(
        uuid.uuid4(), organization_id=org_id, target_format=target_format, filter_criteria={}
    )
    result = await service.process_job(job.id)
    assert result.status == JobStatus.COMPLETED
    assert result.result_storage_key is not None


async def test_export_filters_by_asset_type_status_and_tags(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    org_id = uuid.uuid4()
    matching = await make_asset(
        db_session, organization_id=org_id, name="db-1", asset_type=AssetType.DATABASE
    )
    await make_asset(
        db_session, organization_id=org_id, name="vm-1", asset_type=AssetType.VIRTUAL_MACHINE
    )
    tags = AssetTagService(AssetTagRepository(db_session))
    await tags.assign(matching.id, organization_id=org_id, label="prod")

    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=org_id,
        target_format=ExportFormat.JSON,
        filter_criteria={"asset_type": "database", "status": "discovered", "tags": ["prod"]},
    )
    result = await service.process_job(job.id)
    assert result.total_rows == 1


async def test_export_get_job_and_pending_download_url(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={},
    )
    fetched = await service.get_job(job.id)
    assert fetched.id == job.id
    assert await service.download_url(fetched) is None


async def test_export_process_job_twice_conflicts(
    db_session: AsyncSession, storage_wrapper: StorageWrapper
) -> None:
    service = _export_service(db_session, storage_wrapper)
    job = await service.create_job(
        uuid.uuid4(),
        organization_id=uuid.uuid4(),
        target_format=ExportFormat.JSON,
        filter_criteria={},
    )
    await service.process_job(job.id)
    with pytest.raises(ConflictError):
        await service.process_job(job.id)


__all__: list[str] = []
