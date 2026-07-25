"""Tests for :class:`app.services.resource_authorization.ResourceAuthorizationService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ResourceType, SubjectType
from app.repositories.permission import PermissionRepository
from app.repositories.resource_permission import ResourcePermissionRepository
from app.services.resource_authorization import ResourceAuthorizationService


def _service(db_session: AsyncSession) -> ResourceAuthorizationService:
    return ResourceAuthorizationService(ResourcePermissionRepository(db_session))


async def test_grant_and_read_back(db_session: AsyncSession) -> None:
    service = _service(db_session)
    permission = await PermissionRepository(db_session).get_by_code("reports:read")
    assert permission is not None
    resource_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    await service.grant(
        resource_type=ResourceType.REPORTS,
        resource_id=resource_id,
        subject_type=SubjectType.USER,
        subject_id=subject_id,
        permission_id=permission.id,
        is_owner=True,
        is_public=False,
        granted_by=None,
    )

    grants = await service.grants_for_resource(ResourceType.REPORTS, resource_id)

    assert len(grants) == 1
    assert grants[0].subject_id == subject_id
    assert grants[0].is_owner is True


async def test_grants_for_resource_with_no_grants_is_empty(db_session: AsyncSession) -> None:
    service = _service(db_session)

    grants = await service.grants_for_resource(ResourceType.REPORTS, uuid.uuid4())

    assert grants == []
