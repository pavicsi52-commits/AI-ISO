"""Direct service-layer tests for ``app/services/audit.py`` and
``app/services/activity.py``'s ``list_recent`` methods, not reached
through the API-layer tests alone (no REST surface lists either
directly).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome, ProjectActivityType
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_audit import ProjectAuditRepository
from app.services.activity import ProjectActivityService
from app.services.audit import ProjectAuditService
from tests.conftest import make_project


async def test_activity_record_and_list_recent(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectActivityService(ProjectActivityRepository(db_session))

    await service.record(
        project.id,
        organization_id=project.organization_id,
        activity_type=ProjectActivityType.PROJECT_UPDATED,
        actor_id=uuid.uuid4(),
        description="Updated name",
        detail={"field": "name"},
    )

    recent = await service.list_recent(project.id, limit=10)
    assert len(recent) == 1
    assert recent[0].activity_type == ProjectActivityType.PROJECT_UPDATED


async def test_audit_record_and_list_recent(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectAuditService(ProjectAuditRepository(db_session))

    await service.record(
        project.id,
        organization_id=project.organization_id,
        actor_id=uuid.uuid4(),
        action="settings_update",
        resource_type="project_settings",
        resource_id=uuid.uuid4(),
        outcome=AuditOutcome.SUCCESS,
        reason="admin change",
        before={"a": 1},
        after={"a": 2},
    )

    recent = await service.list_recent(project.id, limit=10)
    assert len(recent) == 1
    assert recent[0].action == "settings_update"
    assert recent[0].before == {"a": 1}
    assert recent[0].after == {"a": 2}
