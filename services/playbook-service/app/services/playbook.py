"""Playbook lifecycle: the definition-level orchestrator.

Per docs/041 "PLAYBOOK MODEL"/"PLAYBOOK STATUS". Creating a playbook
always creates its own first :class:`~app.models.playbook_version
.PlaybookVersion` snapshot in the same call (a playbook with no content
isn't meaningfully "created" yet), publishing both ``PlaybookCreated``
and ``VersionCreated``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent

from app.events.playbook_events import (
    PlaybookArchivedEvent,
    PlaybookCreatedEvent,
    PlaybookDeprecatedEvent,
    PlaybookPublishedEvent,
    PlaybookUpdatedEvent,
)
from app.models.enums import ContentType, PlaybookStatus
from app.models.playbook import Playbook
from app.repositories.playbook import PlaybookRepository
from app.services.audit import PlaybookAuditService
from app.services.version import PlaybookVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_STATUS_EVENTS: dict[PlaybookStatus, type[DomainEvent]] = {
    PlaybookStatus.PUBLISHED: PlaybookPublishedEvent,
    PlaybookStatus.DEPRECATED: PlaybookDeprecatedEvent,
    PlaybookStatus.ARCHIVED: PlaybookArchivedEvent,
}


class PlaybookService:
    """Creates, reads, updates, and deletes playbooks."""

    def __init__(
        self,
        playbooks: PlaybookRepository,
        versions: PlaybookVersionService,
        audit: PlaybookAuditService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._playbooks = playbooks
        self._versions = versions
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, playbook_id: UUID) -> Playbook:
        """Return the playbook identified by *playbook_id*.

        Raises:
            NotFoundError: If no such playbook exists.
        """
        return await self._playbooks.require_by_id(playbook_id)

    async def list_for_org(
        self, organization_id: UUID, *, status: PlaybookStatus | None = None
    ) -> list[Playbook]:
        """Every playbook belonging to *organization_id*."""
        return await self._playbooks.list_for_org(organization_id, status=status)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[Playbook]:
        """Full-text search plus filter plus sort plus pagination ("Search")."""
        return await self._playbooks.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        display_name: str | None,
        description: str | None,
        content_type: ContentType,
        category_id: UUID | None,
        repository_id: UUID | None,
        owner_id: UUID | None,
        author_id: UUID | None,
        entry_file: str | None,
        metadata: dict[str, Any],
        initial_content: str,
        created_by: UUID | None,
    ) -> Playbook:
        """Define a new playbook and its own first content version
        ("Create").

        Raises:
            ContentValidationError: If *initial_content* fails
                structural validation for *content_type*.
        """
        playbook = await self._playbooks.create(
            Playbook(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                display_name=display_name,
                description=description,
                content_type=content_type,
                status=PlaybookStatus.DRAFT,
                category_id=category_id,
                repository_id=repository_id,
                owner_id=owner_id,
                author_id=author_id,
                entry_file=entry_file,
                metadata_=metadata,
            )
        )
        await self._versions.create_version(
            playbook.id,
            content=initial_content,
            release_notes=None,
            change_summary="Initial version.",
            changed_by=created_by,
        )
        await self._audit.record(
            playbook_id=playbook.id,
            organization_id=organization_id,
            actor_id=created_by,
            action="create",
            after={"name": name},
        )
        await self._publish(
            PlaybookCreatedEvent(
                source_service="playbook-service", payload={"playbook_id": str(playbook.id)}
            )
        )
        return await self.get_by_id(playbook.id)

    async def update(
        self,
        playbook_id: UUID,
        *,
        actor_id: UUID | None,
        name: str,
        display_name: str | None,
        description: str | None,
        status: PlaybookStatus,
        category_id: UUID | None,
        repository_id: UUID | None,
        owner_id: UUID | None,
        author_id: UUID | None,
        entry_file: str | None,
        metadata: dict[str, Any],
    ) -> Playbook:
        """Replace a playbook's mutable fields ("Update"), publishing a
        status-transition event when *status* changes to a
        ``PlaybookStatus`` with one (published/deprecated/archived).
        """
        playbook = await self.get_by_id(playbook_id)
        before = {"name": playbook.name, "status": str(playbook.status)}
        status_changed = playbook.status != status

        playbook.name = name
        playbook.display_name = display_name
        playbook.description = description
        playbook.status = status
        playbook.category_id = category_id
        playbook.repository_id = repository_id
        playbook.owner_id = owner_id
        playbook.author_id = author_id
        playbook.entry_file = entry_file
        playbook.metadata_ = metadata
        playbook = await self._playbooks.update(playbook)

        await self._audit.record(
            playbook_id=playbook_id,
            organization_id=playbook.organization_id,
            actor_id=actor_id,
            action="update",
            before=before,
            after={"name": name, "status": str(status)},
        )
        await self._publish(
            PlaybookUpdatedEvent(
                source_service="playbook-service", payload={"playbook_id": str(playbook_id)}
            )
        )
        if status_changed and status in _STATUS_EVENTS:
            await self._publish(
                _STATUS_EVENTS[status](
                    source_service="playbook-service", payload={"playbook_id": str(playbook_id)}
                )
            )
        return playbook

    async def set_status(
        self, playbook_id: UUID, *, status: PlaybookStatus, actor_id: UUID | None
    ) -> Playbook:
        """Transition a playbook's own status without touching any other
        field ("Publish"/deprecate/archive), publishing the matching
        status-transition event.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self.get_by_id(playbook_id)
        before_status = playbook.status
        playbook.status = status
        playbook = await self._playbooks.update(playbook)

        await self._audit.record(
            playbook_id=playbook_id,
            organization_id=playbook.organization_id,
            actor_id=actor_id,
            action="status_change",
            before={"status": str(before_status)},
            after={"status": str(status)},
        )
        if before_status != status and status in _STATUS_EVENTS:
            await self._publish(
                _STATUS_EVENTS[status](
                    source_service="playbook-service", payload={"playbook_id": str(playbook_id)}
                )
            )
        return playbook

    async def delete(self, playbook_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete a playbook ("Delete")."""
        playbook = await self.get_by_id(playbook_id)
        await self._playbooks.delete(playbook_id)
        await self._audit.record(
            playbook_id=playbook_id,
            organization_id=playbook.organization_id,
            actor_id=actor_id,
            action="delete",
        )


__all__ = ["PlaybookService"]
