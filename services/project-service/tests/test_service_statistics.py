"""Direct service-layer tests for ``app/services/statistics.py``'s
recompute-update branch, not reached through the API-layer tests alone.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import OWNER_ROLE_ID
from app.repositories.project_member import ProjectMemberRepository
from app.repositories.project_statistics import ProjectStatisticsRepository
from app.services.statistics import ProjectStatisticsService
from tests.conftest import add_member, make_project


async def test_recompute_creates_then_updates_existing_row(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectStatisticsService(
        ProjectStatisticsRepository(db_session), ProjectMemberRepository(db_session)
    )

    first = await service.recompute(project.id, organization_id=project.organization_id)
    assert first.member_count == 0

    await add_member(
        db_session, project.id, project.organization_id, uuid.uuid4(), role_id=OWNER_ROLE_ID
    )
    second = await service.recompute(project.id, organization_id=project.organization_id)
    assert second.member_count == 1
    assert second.id == first.id
