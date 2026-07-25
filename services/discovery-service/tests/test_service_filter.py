"""Tests for :class:`app.services.filter.DiscoveryFilterService` against
a real (SAVEPOINT-isolated) Postgres session.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FilterAppliesTo
from app.repositories.discovery_filter import DiscoveryFilterRepository
from app.services.filter import DiscoveryFilterService


def _service(session: AsyncSession) -> DiscoveryFilterService:
    return DiscoveryFilterService(DiscoveryFilterRepository(session))


async def test_create_and_list_for_org(db_session: AsyncSession) -> None:
    service = _service(db_session)
    org_id = uuid.uuid4()
    created = await service.create(
        organization_id=org_id,
        name="prod-only",
        applies_to=FilterAppliesTo.TARGET,
        filter_criteria={"environment": "production"},
    )
    assert created.id is not None
    assert created.applies_to == FilterAppliesTo.TARGET

    records = await service.list_for_org(org_id)
    assert {record.id for record in records} == {created.id}


async def test_list_for_org_excludes_other_orgs(db_session: AsyncSession) -> None:
    service = _service(db_session)
    await service.create(
        organization_id=uuid.uuid4(),
        name="other-org-filter",
        applies_to=FilterAppliesTo.ASSET,
        filter_criteria={},
    )
    records = await service.list_for_org(uuid.uuid4())
    assert records == []


async def test_delete_removes_filter(db_session: AsyncSession) -> None:
    service = _service(db_session)
    created = await service.create(
        organization_id=uuid.uuid4(),
        name="to-delete",
        applies_to=FilterAppliesTo.RELATIONSHIP,
        filter_criteria={},
    )
    await service.delete(created.id)
    records = await service.list_for_org(created.organization_id)
    assert records == []


async def test_delete_unknown_filter_raises_not_found(db_session: AsyncSession) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())
