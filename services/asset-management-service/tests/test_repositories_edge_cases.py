"""Direct repository tests for methods not otherwise exercised through
a service's own public surface -- filters/sort branches, due/expiring
lookups, and per-principal listings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.database.filtering import Filter, FilterOperator
from shared_core.database.sorting import SortDirection, SortField
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_assignment import AssetAssignment
from app.models.asset_maintenance import AssetMaintenance
from app.models.asset_maintenance_window import AssetMaintenanceWindow
from app.models.asset_report import AssetReport
from app.models.enums import (
    AssignmentStatus,
    AssignmentType,
    MaintenanceStatus,
    MaintenanceType,
    MaintenanceWindowType,
    ReportType,
)
from app.repositories.asset_assignment import AssetAssignmentRepository
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_maintenance_window import AssetMaintenanceWindowRepository
from app.repositories.asset_report import AssetReportRepository
from app.repositories.managed_asset import ManagedAssetRepository
from tests.conftest import make_managed_asset


async def test_asset_assignment_list_for_assignee(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    assignee_id = uuid.uuid4()
    repo = AssetAssignmentRepository(db_session)
    await repo.create(
        AssetAssignment(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            assignee_id=assignee_id,
            assignment_type=AssignmentType.STANDARD,
            status=AssignmentStatus.ACTIVE,
            assigned_at=datetime.now(UTC),
        )
    )

    assignments = await repo.list_for_assignee(assignee_id)
    assert len(assignments) == 1
    assert assignments[0].assignee_id == assignee_id


async def test_asset_maintenance_list_due_before(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    repo = AssetMaintenanceRepository(db_session)
    now = datetime.now(UTC)
    due_soon = await repo.create(
        AssetMaintenance(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            maintenance_type=MaintenanceType.SCHEDULED,
            status=MaintenanceStatus.SCHEDULED,
            description="Due soon",
            scheduled_at=now - timedelta(hours=1),
        )
    )
    await repo.create(
        AssetMaintenance(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            maintenance_type=MaintenanceType.SCHEDULED,
            status=MaintenanceStatus.COMPLETED,
            description="Already done",
            scheduled_at=now - timedelta(hours=2),
        )
    )

    due = await repo.list_due_before(now)
    assert [item.id for item in due] == [due_soon.id]


async def test_asset_maintenance_window_list_starting_before(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    repo = AssetMaintenanceWindowRepository(db_session)
    now = datetime.now(UTC)
    approved_soon = await repo.create(
        AssetMaintenanceWindow(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            window_type=MaintenanceWindowType.ONE_TIME,
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=1),
            approved=True,
        )
    )
    await repo.create(
        AssetMaintenanceWindow(
            managed_asset_id=managed_asset.id,
            organization_id=managed_asset.organization_id,
            window_type=MaintenanceWindowType.ONE_TIME,
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=1),
            approved=False,
        )
    )

    starting = await repo.list_starting_before(now)
    assert [item.id for item in starting] == [approved_soon.id]


async def test_asset_report_list_for_managed_asset_and_type_filter(
    db_session: AsyncSession,
) -> None:
    managed_asset = await make_managed_asset(db_session)
    repo = AssetReportRepository(db_session)
    await repo.create(
        AssetReport(
            organization_id=managed_asset.organization_id,
            managed_asset_id=managed_asset.id,
            report_type=ReportType.ASSET,
            parameters={},
            result={},
            generated_at=datetime.now(UTC),
        )
    )
    await repo.create(
        AssetReport(
            organization_id=managed_asset.organization_id,
            managed_asset_id=None,
            report_type=ReportType.EXECUTIVE_DASHBOARD,
            parameters={},
            result={},
            generated_at=datetime.now(UTC),
        )
    )

    for_asset = await repo.list_for_managed_asset(managed_asset.id)
    assert len(for_asset) == 1

    filtered = await repo.list_for_org(
        managed_asset.organization_id, report_type=ReportType.EXECUTIVE_DASHBOARD
    )
    assert len(filtered) == 1
    assert filtered[0].report_type == ReportType.EXECUTIVE_DASHBOARD


async def test_managed_asset_search_and_paginate_with_filters_and_sort(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    repo = ManagedAssetRepository(db_session)
    await make_managed_asset(db_session, organization_id=org_id, business_name="Alpha Service")
    await make_managed_asset(db_session, organization_id=org_id, business_name="Beta Service")

    result = await repo.search_and_paginate(
        filters=[Filter(field="organization_id", operator=FilterOperator.EQUAL, value=org_id)],
        sort_fields=[SortField(field="business_name", direction=SortDirection.DESC)],
        page=1,
        page_size=10,
    )

    assert result.metadata.total == 2
    assert [item.business_name for item in result.items] == ["Beta Service", "Alpha Service"]
