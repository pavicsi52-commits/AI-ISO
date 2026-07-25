"""Direct service-layer tests for ``app/services/member.py`` branches
the API-layer tests don't reach: ``set_status`` and rejecting a direct
Owner-role assignment via ``update_role``.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectMemberStatus
from app.models.project_role import ADMINISTRATOR_ROLE_ID, OWNER_ROLE_ID
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_member import ProjectMemberRepository
from app.services.activity import ProjectActivityService
from app.services.member import ProjectMemberService
from tests.conftest import add_member, make_project


def _service(db_session: AsyncSession) -> ProjectMemberService:
    activity = ProjectActivityService(ProjectActivityRepository(db_session))
    return ProjectMemberService(ProjectMemberRepository(db_session), activity)


async def test_set_status_deactivate_and_reactivate(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    user_id = uuid.uuid4()
    await add_member(
        db_session, project.id, project.organization_id, user_id, role_id=ADMINISTRATOR_ROLE_ID
    )
    service = _service(db_session)

    deactivated = await service.set_status(
        project.id, user_id, status=ProjectMemberStatus.SUSPENDED
    )
    assert deactivated.status == ProjectMemberStatus.SUSPENDED

    reactivated = await service.set_status(project.id, user_id, status=ProjectMemberStatus.ACTIVE)
    assert reactivated.status == ProjectMemberStatus.ACTIVE


async def test_update_role_to_owner_rejected(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    user_id = uuid.uuid4()
    await add_member(
        db_session, project.id, project.organization_id, user_id, role_id=ADMINISTRATOR_ROLE_ID
    )
    service = _service(db_session)

    with pytest.raises(BusinessRuleError):
        await service.update_role(
            project.id, user_id, role_id=OWNER_ROLE_ID, organization_id=project.organization_id
        )


async def test_transfer_ownership_when_previous_owner_has_no_membership(
    db_session: AsyncSession,
) -> None:
    """If the project's ``owner_id`` doesn't correspond to any actual
    membership row (a data inconsistency, or a project whose owner left),
    the transfer still succeeds for the new owner -- it just has nothing
    to demote.
    """
    project = await make_project(db_session)
    new_owner = uuid.uuid4()
    await add_member(
        db_session, project.id, project.organization_id, new_owner, role_id=ADMINISTRATOR_ROLE_ID
    )
    service = _service(db_session)

    result = await service.transfer_ownership(
        project.id,
        current_owner_id=uuid.uuid4(),
        new_owner_id=new_owner,
        organization_id=project.organization_id,
    )
    assert result.role_id == OWNER_ROLE_ID


async def test_get_unknown_member_not_found(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.get(project.id, uuid.uuid4())
