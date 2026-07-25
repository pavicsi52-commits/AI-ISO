"""Tests for :class:`app.services.maintenance.MaintenanceService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MaintenanceStatus, MaintenanceType, MaintenanceWindowType
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_maintenance_history import AssetMaintenanceHistoryRepository
from app.repositories.asset_maintenance_window import AssetMaintenanceWindowRepository
from app.services.maintenance import EventPublisher, MaintenanceService
from tests.conftest import make_managed_asset


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> MaintenanceService:
    return MaintenanceService(
        AssetMaintenanceRepository(db_session),
        AssetMaintenanceWindowRepository(db_session),
        AssetMaintenanceHistoryRepository(db_session),
        publish_event=publish_event,
    )


async def test_schedule_creates_activity_and_history_and_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)

    maintenance = await service.schedule(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        maintenance_type=MaintenanceType.PREVENTIVE,
        description="Quarterly checkup",
        scheduled_at=datetime.now(UTC) + timedelta(days=7),
    )

    assert maintenance.status == MaintenanceStatus.SCHEDULED
    history = await service.list_history(managed_asset.id)
    assert len(history) == 1
    assert any(event.event_name == "MaintenanceScheduled" for event in published)


async def test_approve_sets_approver(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    maintenance = await service.schedule(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        maintenance_type=MaintenanceType.SCHEDULED,
        description="Firmware update",
        scheduled_at=datetime.now(UTC),
    )
    approver = uuid.uuid4()

    approved = await service.approve(maintenance.id, approved_by=approver)

    assert approved.approved_by == approver
    assert approved.approved_at is not None


async def test_complete_sets_status_and_publishes(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)
    maintenance = await service.schedule(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        maintenance_type=MaintenanceType.EMERGENCY,
        description="Disk replacement",
        scheduled_at=datetime.now(UTC),
    )

    completed = await service.complete(maintenance.id, actor_id=uuid.uuid4())

    assert completed.status == MaintenanceStatus.COMPLETED
    assert completed.completed_at is not None
    assert any(event.event_name == "MaintenanceCompleted" for event in published)


async def test_create_window_rejects_invalid_range(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        await service.create_window(
            managed_asset.id,
            organization_id=managed_asset.organization_id,
            window_type=MaintenanceWindowType.ONE_TIME,
            starts_at=now,
            ends_at=now - timedelta(hours=1),
            recurrence_rule=None,
        )


async def test_create_window_success(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    now = datetime.now(UTC)

    window = await service.create_window(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        window_type=MaintenanceWindowType.RECURRING,
        starts_at=now,
        ends_at=now + timedelta(hours=2),
        recurrence_rule="FREQ=WEEKLY",
    )

    assert window.window_type == MaintenanceWindowType.RECURRING
    windows = await service.list_windows(managed_asset.id)
    assert len(windows) == 1


async def test_list_for_managed_asset(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    await service.schedule(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        maintenance_type=MaintenanceType.CORRECTIVE,
        description="Fix",
        scheduled_at=datetime.now(UTC),
    )

    records = await service.list_for_managed_asset(managed_asset.id)
    assert len(records) == 1
