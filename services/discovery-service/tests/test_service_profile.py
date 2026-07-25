"""Tests for :class:`app.services.profile.DiscoveryProfileService`
against a real (SAVEPOINT-isolated) Postgres session.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.discovery_events import DiscoveryProfileCreatedEvent
from app.models.enums import ProfileType, ProtocolType
from app.repositories.discovery_profile import DiscoveryProfileRepository
from app.services.profile import DiscoveryProfileService


def _service(session: AsyncSession) -> DiscoveryProfileService:
    return DiscoveryProfileService(DiscoveryProfileRepository(session))


async def test_create_and_get_by_id(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    profile = await service.create(
        organization_id=org_id,
        name="quick-scan",
        description="A quick scan.",
        profile_type=ProfileType.QUICK_SCAN,
        protocols=[ProtocolType.TCP, ProtocolType.ICMP],
        default_ports={"tcp": 22},
        timeout_seconds=10,
        concurrency_limit=5,
    )
    assert profile.id is not None
    assert profile.protocols == ["tcp", "icmp"]
    assert profile.is_system is False

    found = await service.get_by_id(profile.id)
    assert found.name == "quick-scan"


async def test_create_publishes_event(db_session: AsyncSession) -> None:
    published: list[object] = []

    async def _publish(event: object) -> None:
        published.append(event)

    service = DiscoveryProfileService(
        DiscoveryProfileRepository(db_session), publish_event=_publish
    )
    org_id = uuid.uuid4()
    profile = await service.create(
        organization_id=org_id,
        name="event-profile",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    assert len(published) == 1
    event = published[0]
    assert isinstance(event, DiscoveryProfileCreatedEvent)
    assert event.payload["profile_id"] == str(profile.id)


async def test_create_duplicate_name_raises_conflict(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        name="dup-name",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    with pytest.raises(ConflictError):
        await service.create(
            organization_id=org_id,
            name="dup-name",
            description=None,
            profile_type=ProfileType.CUSTOM,
            protocols=[],
            default_ports={},
            timeout_seconds=30,
            concurrency_limit=10,
        )


async def test_same_name_different_org_is_allowed(db_session: AsyncSession) -> None:
    service = _service(db_session)
    name = "shared-name"
    profile_a = await service.create(
        organization_id=uuid.uuid4(),
        name=name,
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    profile_b = await service.create(
        organization_id=uuid.uuid4(),
        name=name,
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    assert profile_a.id != profile_b.id


async def test_list_for_org(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    await service.create(
        organization_id=org_id,
        name="p1",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    await service.create(
        organization_id=org_id,
        name="p2",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    await service.create(
        organization_id=uuid.uuid4(),
        name="other-org",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    records = await service.list_for_org(org_id)
    assert {record.name for record in records} == {"p1", "p2"}


async def test_update_replaces_mutable_fields(db_session: AsyncSession) -> None:
    service = _service(db_session)
    profile = await service.create(
        organization_id=uuid.uuid4(),
        name="to-update",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[ProtocolType.TCP],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    updated = await service.update(
        profile.id,
        name="renamed",
        description="now described",
        profile_type=ProfileType.DEEP_SCAN,
        protocols=[ProtocolType.SSH, ProtocolType.HTTP],
        default_ports={"ssh": 22},
        timeout_seconds=60,
        concurrency_limit=20,
    )
    assert updated.name == "renamed"
    assert updated.description == "now described"
    assert updated.profile_type == ProfileType.DEEP_SCAN
    assert updated.protocols == ["ssh", "http"]
    assert updated.timeout_seconds == 60
    assert updated.concurrency_limit == 20


async def test_update_unknown_profile_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.update(
            uuid.uuid4(),
            name="x",
            description=None,
            profile_type=ProfileType.CUSTOM,
            protocols=[],
            default_ports={},
            timeout_seconds=30,
            concurrency_limit=10,
        )


async def test_delete_removes_profile(db_session: AsyncSession) -> None:
    service = _service(db_session)
    profile = await service.create(
        organization_id=uuid.uuid4(),
        name="to-delete",
        description=None,
        profile_type=ProfileType.CUSTOM,
        protocols=[],
        default_ports={},
        timeout_seconds=30,
        concurrency_limit=10,
    )
    await service.delete(profile.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(profile.id)


async def test_delete_unknown_profile_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())
