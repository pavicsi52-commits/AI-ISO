"""Tests for ``app/api/import_.py`` and ``app/api/export.py``.

Exercises the real HTTP layer through to a queued job -- ``process_job``
itself is invoked directly here (mirroring what the real queue consumer
would do) rather than waiting on the background worker/RabbitMQ round
trip, keeping these tests fast and deterministic; ``test_workers.py``
covers the queue-consumer wiring itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.asset import AssetRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_tag import AssetTagRepository
from app.services.export_service import AssetExportService
from app.services.import_service import AssetImportService
from app.topology.graph import TopologyGraphClient
from tests.conftest import build_asset_service


async def test_start_import_and_get_job(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    files = {
        "file": ("assets.json", b'[{"name": "a", "asset_type": "database"}]', "application/json")
    }

    response = await client.post(
        "/inventory/import",
        params={"organization_id": str(org_id), "source_format": "json", "preview_only": "false"},
        files=files,
        headers=headers,
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    assert response.json()["data"]["status"] == "queued"

    # Process the job directly, as the real queue worker would.
    assets = build_asset_service(db_session, topology_graph_client)
    service = AssetImportService(
        AssetImportJobRepository(db_session),
        assets,
        storage_wrapper,
        db_session,
        bucket="inventory-import-export-test",
    )
    await service.process_job(uuid.UUID(job_id))

    get_response = await client.get(f"/inventory/import/{job_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["succeeded_rows"] == 1


async def test_import_requires_auth(client: AsyncClient) -> None:
    files = {"file": ("assets.json", b"[]", "application/json")}
    response = await client.post(
        "/inventory/import",
        params={"organization_id": str(uuid.uuid4())},
        files=files,
    )
    assert response.status_code == 401


async def test_rollback_import_job(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    storage_wrapper: StorageWrapper,
    topology_graph_client: TopologyGraphClient,
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    files = {
        "file": ("assets.json", b'[{"name": "a", "asset_type": "database"}]', "application/json")
    }
    response = await client.post(
        "/inventory/import",
        params={"organization_id": str(org_id), "source_format": "json", "preview_only": "false"},
        files=files,
        headers=headers,
    )
    job_id = response.json()["data"]["job_id"]

    assets = build_asset_service(db_session, topology_graph_client)
    service = AssetImportService(
        AssetImportJobRepository(db_session),
        assets,
        storage_wrapper,
        db_session,
        bucket="inventory-import-export-test",
    )
    await service.process_job(uuid.UUID(job_id))

    rollback_response = await client.post(f"/inventory/import/{job_id}/rollback", headers=headers)
    assert rollback_response.status_code == 200


async def test_start_export_and_get_job(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    storage_wrapper: StorageWrapper,
) -> None:
    org_id = uuid.uuid4()
    headers = auth_headers(uuid.uuid4())
    await client.post(
        "/inventory/assets",
        json={"organization_id": str(org_id), "name": "exportable", "asset_type": "database"},
        headers=headers,
    )

    response = await client.post(
        "/inventory/export",
        json={"organization_id": str(org_id), "target_format": "json"},
        headers=headers,
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]

    service = AssetExportService(
        AssetExportJobRepository(db_session),
        AssetRepository(db_session),
        AssetTagRepository(db_session),
        storage_wrapper,
        db_session,
        bucket="inventory-import-export-test",
    )
    await service.process_job(uuid.UUID(job_id))

    get_response = await client.get(f"/inventory/export/{job_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["download_url"] is not None


async def test_export_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/inventory/export", json={"organization_id": str(uuid.uuid4()), "target_format": "json"}
    )
    assert response.status_code == 401


__all__: list[str] = []
