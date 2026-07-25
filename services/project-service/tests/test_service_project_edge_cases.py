"""Direct service-layer tests for ``app/services/project.py``'s
``patch()`` -- exercises every individual field branch, which the
API-layer test (``test_patch_project_partial_update``, only patching
``category``) doesn't reach on its own.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectPriority, ProjectStatus, ProjectVisibility
from app.repositories.project import ProjectRepository
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_archive import ProjectArchiveRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService
from app.services.project import ProjectService
from tests.conftest import make_project


def _service(db_session: AsyncSession) -> ProjectService:
    activity = ProjectActivityService(ProjectActivityRepository(db_session))
    archives = ProjectArchiveService(ProjectArchiveRepository(db_session))
    return ProjectService(
        ProjectRepository(db_session),
        ProjectSettingsRepository(db_session),
        ProjectPreferencesRepository(db_session),
        activity,
        archives,
        publish_event=None,
    )


async def test_patch_every_field(db_session: AsyncSession) -> None:
    project = await make_project(db_session, name="Original", code="patch-all")
    service = _service(db_session)

    updated = await service.patch(
        project.id,
        name="New Name",
        display_name="Display",
        description="Desc",
        status=ProjectStatus.ACTIVE,
        visibility=ProjectVisibility.PUBLIC,
        default_language="fr",
        timezone="Europe/Paris",
        category="industrial",
        priority=ProjectPriority.CRITICAL,
        metadata={"k": "v"},
    )

    assert updated.name == "New Name"
    assert updated.display_name == "Display"
    assert updated.description == "Desc"
    assert updated.status == ProjectStatus.ACTIVE
    assert updated.visibility == ProjectVisibility.PUBLIC
    assert updated.default_language == "fr"
    assert updated.timezone == "Europe/Paris"
    assert updated.category == "industrial"
    assert updated.priority == ProjectPriority.CRITICAL
    assert updated.metadata_ == {"k": "v"}


async def test_patch_no_fields_is_a_no_op(db_session: AsyncSession) -> None:
    project = await make_project(db_session, name="Untouched")
    service = _service(db_session)

    updated = await service.patch(project.id)

    assert updated.name == "Untouched"
