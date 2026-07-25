"""Tests for :class:`app.services.drift.ConfigurationDriftService`."""

from __future__ import annotations

import uuid

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DriftStatus, DriftType
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.services.drift import ConfigurationDriftService, EventPublisher
from tests.conftest import make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationDriftService:
    return ConfigurationDriftService(
        ConfigurationDriftRepository(db_session), publish_event=publish_event
    )


async def test_report_creates_drift_and_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)
    managed_asset_id = uuid.uuid4()

    drift = await service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=managed_asset_id,
        drift_type=DriftType.UNEXPECTED_CHANGES,
        details={"field": "port", "expected": "80", "actual": "8080"},
    )

    assert drift.status == DriftStatus.DETECTED
    assert any(event.event_name == "DriftDetected" for event in published)


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.VERSION_DRIFT,
        details={},
    )

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1


async def test_list_unresolved_for_org(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    drift = await service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.POLICY_DRIFT,
        details={},
    )

    unresolved = await service.list_unresolved_for_org(profile.organization_id)
    assert len(unresolved) == 1

    await service.resolve(drift.id, status=DriftStatus.RESOLVED, resolved_by=uuid.uuid4())
    unresolved_after = await service.list_unresolved_for_org(profile.organization_id)
    assert unresolved_after == []


async def test_resolve_sets_resolved_at(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    drift = await service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.TEMPLATE_DRIFT,
        details={},
    )

    resolver_id = uuid.uuid4()
    resolved = await service.resolve(drift.id, status=DriftStatus.RESOLVED, resolved_by=resolver_id)

    assert resolved.status == DriftStatus.RESOLVED
    assert resolved.resolved_by == resolver_id
    assert resolved.resolved_at is not None


async def test_resolve_to_ignored_does_not_set_resolved_at(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    drift = await service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.VARIABLE_DRIFT,
        details={},
    )

    ignored = await service.resolve(drift.id, status=DriftStatus.IGNORED, resolved_by=None)
    assert ignored.status == DriftStatus.IGNORED
    assert ignored.resolved_at is None
