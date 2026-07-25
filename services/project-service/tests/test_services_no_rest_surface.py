"""Direct service-layer tests for project sub-resources docs/034 never
names a REST endpoint for: favorites, integrations, labels, metadata,
preferences, notes, resources, and tags. Each of these services exists
for programmatic completeness only (see each module's own docstring),
so they're exercised directly against the repository layer rather than
through HTTP.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectResourceType
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_favorite import ProjectFavoriteRepository
from app.repositories.project_integration import ProjectIntegrationRepository
from app.repositories.project_label import ProjectLabelRepository
from app.repositories.project_metadata import ProjectMetadataRepository
from app.repositories.project_note import ProjectNoteRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_resource import ProjectResourceRepository
from app.repositories.project_tag import ProjectTagRepository
from app.services.activity import ProjectActivityService
from app.services.favorite import ProjectFavoriteService
from app.services.integration import ProjectIntegrationService
from app.services.label import ProjectLabelService
from app.services.metadata import ProjectMetadataService
from app.services.note import ProjectNoteService
from app.services.preferences import ProjectPreferencesService
from app.services.resource import ProjectResourceService
from app.services.tag import ProjectTagService
from tests.conftest import make_project


async def test_favorite_mark_list_and_unmark(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    user_id = uuid.uuid4()
    service = ProjectFavoriteService(ProjectFavoriteRepository(db_session))

    marked = await service.mark(project.id, user_id, organization_id=project.organization_id)
    assert marked.project_id == project.id

    # Idempotent: marking again returns the same row.
    again = await service.mark(project.id, user_id, organization_id=project.organization_id)
    assert again.id == marked.id

    listing = await service.list_for_user(user_id)
    assert [f.id for f in listing] == [marked.id]

    await service.unmark(project.id, user_id)
    assert await service.list_for_user(user_id) == []

    # Unmarking again is a no-op, not an error.
    await service.unmark(project.id, user_id)


async def test_integration_create_enable_and_remove(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectIntegrationService(ProjectIntegrationRepository(db_session))

    created = await service.create(
        project.id,
        organization_id=project.organization_id,
        name="Slack",
        integration_type="webhook",
        external_reference_id=None,
        config={"url": "https://example.com"},
    )
    assert created.is_enabled is True

    with pytest.raises(ConflictError):
        await service.create(
            project.id,
            organization_id=project.organization_id,
            name="Slack",
            integration_type="webhook",
            external_reference_id=None,
            config={},
        )

    disabled = await service.set_enabled(project.id, created.id, is_enabled=False)
    assert disabled.is_enabled is False

    listing = await service.list_for_project(project.id)
    assert [i.id for i in listing] == [created.id]

    await service.remove(project.id, created.id)
    assert await service.list_for_project(project.id) == []


async def test_integration_set_enabled_wrong_project_not_found(db_session: AsyncSession) -> None:
    project_a = await make_project(db_session)
    project_b = await make_project(db_session)
    service = ProjectIntegrationService(ProjectIntegrationRepository(db_session))
    integration = await service.create(
        project_a.id,
        organization_id=project_a.organization_id,
        name="Webhook",
        integration_type="webhook",
        external_reference_id=None,
        config={},
    )

    with pytest.raises(NotFoundError):
        await service.set_enabled(project_b.id, integration.id, is_enabled=False)

    with pytest.raises(NotFoundError):
        await service.remove(project_b.id, integration.id)


async def test_label_set_list_and_remove(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectLabelService(ProjectLabelRepository(db_session))

    created = await service.set(
        project.id, "env", "prod", organization_id=project.organization_id, color="#ff0000"
    )
    assert created.value == "prod"

    overwritten = await service.set(
        project.id, "env", "staging", organization_id=project.organization_id
    )
    assert overwritten.id == created.id
    assert overwritten.value == "staging"

    listing = await service.list_for_project(project.id)
    assert len(listing) == 1

    await service.remove(project.id, "env")
    assert await service.list_for_project(project.id) == []
    # No-op if already removed.
    await service.remove(project.id, "env")


async def test_metadata_set_list_and_remove(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectMetadataService(ProjectMetadataRepository(db_session))

    created = await service.set(
        project.id, "cost_center", "CC-1", organization_id=project.organization_id
    )
    assert created.value == "CC-1"

    overwritten = await service.set(
        project.id, "cost_center", "CC-2", organization_id=project.organization_id
    )
    assert overwritten.id == created.id

    listing = await service.list_for_project(project.id)
    assert len(listing) == 1

    await service.remove(project.id, "cost_center")
    assert await service.list_for_project(project.id) == []
    await service.remove(project.id, "cost_center")


async def test_preferences_get_or_create_defaults_then_update(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectPreferencesService(ProjectPreferencesRepository(db_session))

    defaults = await service.get_or_create(project.id, organization_id=project.organization_id)
    assert defaults.project_id == project.id

    updated = await service.update(
        project.id,
        organization_id=project.organization_id,
        dashboard_layout={"widgets": ["usage"]},
        notification_preferences={"email": True},
        ui_preferences={"density": "compact"},
    )
    assert updated.dashboard_layout == {"widgets": ["usage"]}


async def test_note_create_list_and_remove(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    author = uuid.uuid4()
    service = ProjectNoteService(ProjectNoteRepository(db_session))

    note = await service.create(
        project.id,
        organization_id=project.organization_id,
        author_id=author,
        title="Kickoff",
        content="Notes from kickoff meeting.",
        is_pinned=True,
    )
    assert note.is_pinned is True

    listing = await service.list_for_project(project.id)
    assert [n.id for n in listing] == [note.id]

    await service.remove(project.id, note.id)
    assert await service.list_for_project(project.id) == []


async def test_note_remove_wrong_project_not_found(db_session: AsyncSession) -> None:
    project_a = await make_project(db_session)
    project_b = await make_project(db_session)
    service = ProjectNoteService(ProjectNoteRepository(db_session))
    note = await service.create(
        project_a.id,
        organization_id=project_a.organization_id,
        author_id=uuid.uuid4(),
        title=None,
        content="x",
    )

    with pytest.raises(NotFoundError):
        await service.remove(project_b.id, note.id)


async def test_resource_link_list_and_unlink(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    activity = ProjectActivityService(ProjectActivityRepository(db_session))
    service = ProjectResourceService(ProjectResourceRepository(db_session), activity)
    resource_id = uuid.uuid4()

    linked = await service.link(
        project.id,
        organization_id=project.organization_id,
        resource_type=ProjectResourceType.CONNECTOR,
        resource_id=resource_id,
        name="Primary Connector",
        linked_by=uuid.uuid4(),
    )
    assert linked.resource_id == resource_id

    with pytest.raises(ConflictError):
        await service.link(
            project.id,
            organization_id=project.organization_id,
            resource_type=ProjectResourceType.CONNECTOR,
            resource_id=resource_id,
            name=None,
            linked_by=None,
        )

    listing = await service.list_for_project(project.id)
    assert [r.id for r in listing] == [linked.id]

    await service.unlink(project.id, linked.id, organization_id=project.organization_id)
    assert await service.list_for_project(project.id) == []


async def test_resource_unlink_wrong_project_not_found(db_session: AsyncSession) -> None:
    project_a = await make_project(db_session)
    project_b = await make_project(db_session)
    activity = ProjectActivityService(ProjectActivityRepository(db_session))
    service = ProjectResourceService(ProjectResourceRepository(db_session), activity)
    linked = await service.link(
        project_a.id,
        organization_id=project_a.organization_id,
        resource_type=ProjectResourceType.DASHBOARD,
        resource_id=uuid.uuid4(),
        name=None,
        linked_by=None,
    )

    with pytest.raises(NotFoundError):
        await service.unlink(project_b.id, linked.id, organization_id=project_b.organization_id)


async def test_tag_assign_list_and_remove(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectTagService(ProjectTagRepository(db_session))

    tag = await service.assign(
        project.id, organization_id=project.organization_id, label="critical", category="priority"
    )
    listing = await service.list_for_project(project.id)
    assert [t.id for t in listing] == [tag.id]

    with pytest.raises(ConflictError):
        await service.assign(
            project.id, organization_id=project.organization_id, label="critical", category=None
        )

    await service.remove(project.id, tag.id)
    assert await service.list_for_project(project.id) == []


async def test_tag_remove_wrong_project_not_found(db_session: AsyncSession) -> None:
    project_a = await make_project(db_session)
    project_b = await make_project(db_session)
    service = ProjectTagService(ProjectTagRepository(db_session))
    tag = await service.assign(
        project_a.id, organization_id=project_a.organization_id, label="x", category=None
    )

    with pytest.raises(NotFoundError):
        await service.remove(project_b.id, tag.id)


async def test_tag_remove_unknown_id_not_found(db_session: AsyncSession) -> None:
    project = await make_project(db_session)
    service = ProjectTagService(ProjectTagRepository(db_session))
    with pytest.raises(NotFoundError):
        await service.remove(project.id, uuid.uuid4())
