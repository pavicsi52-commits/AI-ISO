"""Tests for :class:`AssetDiscoveryLinkService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DiscoverySource
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository
from app.services.discovery_link import AssetDiscoveryLinkService
from tests.conftest import make_asset


def _service(db_session: AsyncSession) -> AssetDiscoveryLinkService:
    return AssetDiscoveryLinkService(AssetDiscoveryLinkRepository(db_session))


async def test_record_and_list(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    link = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        source=DiscoverySource.CLOUD_API,
        external_id="i-1234",
    )
    assert link.external_id == "i-1234"
    records = await service.list_for_asset(asset.id)
    assert [r.id for r in records] == [link.id]


async def test_record_refreshes_existing(db_session: AsyncSession) -> None:
    service = _service(db_session)
    asset = await make_asset(db_session)
    first = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        source=DiscoverySource.AGENT,
        external_id="agent-1",
    )
    second = await service.record(
        asset.id,
        organization_id=asset.organization_id,
        source=DiscoverySource.AGENT,
        external_id="agent-1",
    )
    assert first.id == second.id
    assert second.last_seen_at >= first.last_seen_at


__all__: list[str] = []
