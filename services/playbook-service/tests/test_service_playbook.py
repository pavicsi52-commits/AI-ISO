"""Tests for :class:`app.services.playbook.PlaybookService`."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType, PlaybookStatus
from app.models.playbook import Playbook
from app.services.playbook import PlaybookService
from tests.conftest import build_playbook_service


async def _create_playbook(
    service: PlaybookService, *, organization_id: UUID | None = None, name: str = "deploy-app"
) -> Playbook:
    return await service.create(
        organization_id=organization_id or uuid.uuid4(),
        project_id=None,
        name=name,
        display_name="Deploy App",
        description="Deploys the app.",
        content_type=ContentType.SHELL_SCRIPT,
        category_id=None,
        repository_id=None,
        owner_id=None,
        author_id=None,
        entry_file=None,
        metadata={},
        initial_content="echo deploying",
        created_by=None,
    )


class TestPlaybookService:
    async def test_create_creates_playbook_and_first_version(
        self, db_session: AsyncSession
    ) -> None:
        service = build_playbook_service(db_session)
        playbook = await _create_playbook(service)
        assert playbook.name == "deploy-app"
        assert playbook.status == PlaybookStatus.DRAFT
        assert playbook.current_version == "1.0.0"

    async def test_create_publishes_playbook_and_version_events(
        self, db_session: AsyncSession
    ) -> None:
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = build_playbook_service(db_session, publish_event=_collect)
        await _create_playbook(service)
        event_names = {event.event_name for event in events}
        assert event_names == {"PlaybookCreated", "VersionCreated"}

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = build_playbook_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org_filters_by_status(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = build_playbook_service(db_session)
        await _create_playbook(service, organization_id=org_id, name="draft-one")
        published = await _create_playbook(service, organization_id=org_id, name="published-one")
        await service.set_status(published.id, status=PlaybookStatus.PUBLISHED, actor_id=None)

        drafts = await service.list_for_org(org_id, status=PlaybookStatus.DRAFT)
        assert [p.name for p in drafts] == ["draft-one"]

    async def test_update_changes_fields_and_publishes_status_event(
        self, db_session: AsyncSession
    ) -> None:
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = build_playbook_service(db_session, publish_event=_collect)
        playbook = await _create_playbook(service)
        events.clear()

        updated = await service.update(
            playbook.id,
            actor_id=None,
            name="deploy-app-renamed",
            display_name="Deploy App Renamed",
            description="Updated description.",
            status=PlaybookStatus.PUBLISHED,
            category_id=None,
            repository_id=None,
            owner_id=None,
            author_id=None,
            entry_file=None,
            metadata={"k": "v"},
        )
        assert updated.name == "deploy-app-renamed"
        assert updated.status == PlaybookStatus.PUBLISHED
        event_names = {event.event_name for event in events}
        assert event_names == {"PlaybookUpdated", "PlaybookPublished"}

    async def test_update_without_status_change_only_publishes_updated_event(
        self, db_session: AsyncSession
    ) -> None:
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = build_playbook_service(db_session, publish_event=_collect)
        playbook = await _create_playbook(service)
        events.clear()

        await service.update(
            playbook.id,
            actor_id=None,
            name="deploy-app",
            display_name="Deploy App",
            description="Same status.",
            status=PlaybookStatus.DRAFT,
            category_id=None,
            repository_id=None,
            owner_id=None,
            author_id=None,
            entry_file=None,
            metadata={},
        )
        event_names = [event.event_name for event in events]
        assert event_names == ["PlaybookUpdated"]

    async def test_set_status_transitions_and_publishes(self, db_session: AsyncSession) -> None:
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = build_playbook_service(db_session, publish_event=_collect)
        playbook = await _create_playbook(service)
        events.clear()

        updated = await service.set_status(
            playbook.id, status=PlaybookStatus.ARCHIVED, actor_id=None
        )
        assert updated.status == PlaybookStatus.ARCHIVED
        assert [event.event_name for event in events] == ["PlaybookArchived"]

    async def test_delete_soft_deletes(self, db_session: AsyncSession) -> None:
        service = build_playbook_service(db_session)
        playbook = await _create_playbook(service)
        await service.delete(playbook.id, actor_id=None)
        with pytest.raises(NotFoundError):
            await service.get_by_id(playbook.id)

    async def test_search_finds_created_playbook(self, db_session: AsyncSession) -> None:
        service = build_playbook_service(db_session)
        await _create_playbook(service, name="searchable-playbook")

        result = await service.search(
            query="searchable", filters=None, sort_fields=None, page=1, page_size=10
        )
        assert result.metadata.total >= 1
        assert any(p.name == "searchable-playbook" for p in result.items)
