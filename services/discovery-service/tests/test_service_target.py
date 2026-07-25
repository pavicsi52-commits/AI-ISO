"""Tests for :class:`app.services.target.DiscoveryTargetService`
against a real (SAVEPOINT-isolated) Postgres session.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import seed_profile

from app.models.enums import ProtocolType, TargetType
from app.repositories.discovery_target import DiscoveryTargetRepository
from app.services.target import DiscoveryTargetService


def _service(session: AsyncSession) -> DiscoveryTargetService:
    return DiscoveryTargetService(DiscoveryTargetRepository(session))


async def test_create_target(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    target = await service.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="192.0.2.10",
        protocol=ProtocolType.TCP,
        port=443,
        metadata={"note": "test"},
    )
    assert target.id is not None
    assert target.address == "192.0.2.10"
    assert target.port == 443
    assert target.is_active is True
    assert target.metadata_ == {"note": "test"}


async def test_create_target_defaults(db_session: AsyncSession) -> None:
    service = _service(db_session)
    target = await service.create(
        organization_id=uuid.uuid4(),
        profile_id=None,
        target_type=TargetType.CUSTOM,
        address="example.internal",
        protocol=ProtocolType.DNS,
    )
    assert target.profile_id is None
    assert target.port is None
    assert target.credential_id is None
    assert target.metadata_ == {}


async def test_list_for_profile_only_returns_active_targets_for_that_profile(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    profile = await seed_profile(db_session, organization_id=org_id)
    other_profile = await seed_profile(db_session, organization_id=org_id)

    await service.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="a",
        protocol=ProtocolType.TCP,
    )
    await service.create(
        organization_id=org_id,
        profile_id=profile.id,
        target_type=TargetType.HOST,
        address="b",
        protocol=ProtocolType.TCP,
    )
    await service.create(
        organization_id=org_id,
        profile_id=other_profile.id,
        target_type=TargetType.HOST,
        address="c",
        protocol=ProtocolType.TCP,
    )

    records = await service.list_for_profile(profile.id)
    assert {record.address for record in records} == {"a", "b"}
