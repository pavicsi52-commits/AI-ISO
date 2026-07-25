"""Direct service-layer tests for ``app/services/member.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import make_org

from app.models.enums import MemberRole
from app.repositories.activity import OrganizationActivityRepository
from app.repositories.member import OrganizationMemberRepository
from app.services.activity import OrganizationActivityService
from app.services.member import OrganizationMemberService


def _make_service(db_session: AsyncSession) -> OrganizationMemberService:
    activity = OrganizationActivityService(OrganizationActivityRepository(db_session))
    return OrganizationMemberService(OrganizationMemberRepository(db_session), activity)


async def test_add_get_list_and_remove(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    user_id = uuid.uuid4()
    service = _make_service(db_session)

    added = await service.add(organization.id, user_id, role=MemberRole.ADMIN)
    assert added.role == MemberRole.ADMIN

    fetched = await service.get(organization.id, user_id)
    assert fetched.id == added.id

    listing = await service.list_for_org(organization.id)
    assert [m.id for m in listing] == [added.id]

    await service.remove(organization.id, user_id)
    assert await service.list_for_org(organization.id) == []


async def test_get_unknown_member_not_found(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = _make_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get(organization.id, uuid.uuid4())


async def test_remove_unknown_member_not_found(db_session: AsyncSession) -> None:
    organization = await make_org(db_session)
    service = _make_service(db_session)
    with pytest.raises(NotFoundError):
        await service.remove(organization.id, uuid.uuid4())
