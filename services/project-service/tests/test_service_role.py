"""Direct service-layer tests for ``app/services/role.py``."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import SYSTEM_ROLE_RANKS
from app.repositories.project_role import ProjectRoleRepository
from app.services.role import ProjectRoleService
from tests.conftest import make_project


async def test_get_by_code_system_role(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectRoleService(ProjectRoleRepository(db_session))

    role = await service.get_by_code(project.id, "viewer")
    assert role.code == "viewer"
    assert role.is_system is True


async def test_get_by_code_not_found(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectRoleService(ProjectRoleRepository(db_session))

    with pytest.raises(NotFoundError):
        await service.get_by_code(project.id, "not-a-real-role")


async def test_get_by_id_not_found(db_session: AsyncSession) -> None:
    service = ProjectRoleService(ProjectRoleRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_available_includes_system_roles(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectRoleService(ProjectRoleRepository(db_session))

    roles = await service.list_available(project.id)
    codes = {r.code for r in roles}
    assert {"owner", "administrator", "viewer", "auditor"} <= codes


async def test_create_custom_role(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectRoleService(ProjectRoleRepository(db_session))

    custom = await service.create_custom(
        project.id,
        organization_id=project.organization_id,
        name="Release Manager",
        code="release_manager",
        rank=60,
        description="Manages releases.",
    )
    assert custom.is_system is False
    assert custom.rank == 60

    fetched = await service.get_by_code(project.id, "release_manager")
    assert fetched.id == custom.id


async def test_create_custom_role_cannot_outrank_owner(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectRoleService(ProjectRoleRepository(db_session))

    with pytest.raises(BusinessRuleError):
        await service.create_custom(
            project.id,
            organization_id=project.organization_id,
            name="Super Owner",
            code="super_owner",
            rank=SYSTEM_ROLE_RANKS["owner"],
            description=None,
        )
