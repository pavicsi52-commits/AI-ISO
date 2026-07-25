"""Tests for :class:`app.services.lifecycle.LifecycleService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LifecycleState, ManagedAssetStatus
from tests.conftest import build_lifecycle_service, make_managed_asset


async def test_record_change_lists_newest_first(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session)

    await service.record_change(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        event_type="created",
        detail={},
    )
    await service.record_change(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        actor_id=None,
        event_type="updated",
        detail={},
    )

    history = await service.list_history(managed_asset.id)
    assert [entry.event_type for entry in history] == ["updated", "created"]


async def test_retire_sets_status_and_publishes_events(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session, publish_event=_publish)

    retirement = await service.retire(managed_asset.id, actor_id=uuid.uuid4(), reason="EOL")

    assert managed_asset.status == ManagedAssetStatus.RETIRED
    assert managed_asset.lifecycle_state == LifecycleState.RETIRED
    assert managed_asset.retirement_date is not None
    assert retirement.reason == "EOL"
    event_names = {event.event_name for event in published}
    assert "AssetRetired" in event_names
    assert "LifecycleChanged" in event_names


async def test_retire_twice_updates_same_record(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session)

    first = await service.retire(managed_asset.id, actor_id=None, reason="first")
    second = await service.retire(managed_asset.id, actor_id=None, reason="second")

    assert first.id == second.id
    assert second.reason == "second"


async def test_dispose_requires_prior_retirement(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session)

    with pytest.raises(NotFoundError):
        await service.dispose(
            managed_asset.id, actor_id=None, disposal_method="recycled", residual_value_realized=0
        )


async def test_dispose_sets_disposed_status(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session)
    await service.retire(managed_asset.id, actor_id=None, reason="EOL")

    retirement = await service.dispose(
        managed_asset.id,
        actor_id=None,
        disposal_method="recycled",
        residual_value_realized=10.0,
    )

    assert managed_asset.status == ManagedAssetStatus.DISPOSED
    assert managed_asset.lifecycle_state == LifecycleState.DISPOSED
    assert retirement.disposal_method == "recycled"
    assert retirement.disposed_at is not None


async def test_get_retirement_returns_none_when_never_retired(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = build_lifecycle_service(db_session)
    assert await service.get_retirement(managed_asset.id) is None
