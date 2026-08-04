"""Post-incident reviews: authoring, action items, approval, publication.

A postmortem's lifecycle -- draft, review, approval, publication -- is
deliberately linear and one-way except for the review step, which can
send it back to draft. There is no reopening a published postmortem:
a correction to a published document is a new note added to it, the
same reasoning ``app/models/timeline.py`` applies to the incident
timeline itself, not a rewrite of what was already shared.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.incident_events import SOURCE_SERVICE, PostmortemCompletedEvent
from app.models.enums import (
    TERMINAL_INCIDENT_STATUSES,
    ActionItemStatus,
    IncidentStatus,
    PostmortemStatus,
    action_item_status_of,
    incident_status_of,
    postmortem_status_of,
)
from app.models.postmortem import Postmortem, PostmortemActionItem
from app.repositories.incident import IncidentRepository
from app.repositories.postmortem import ActionItemRepository, PostmortemRepository
from app.types import EventPublisher

logger = get_logger("app.services.postmortem")

_CLOSED_INCIDENT_STATUSES = TERMINAL_INCIDENT_STATUSES | {IncidentStatus.RESOLVED}

_ALLOWED_TRANSITIONS: dict[PostmortemStatus, frozenset[PostmortemStatus]] = {
    PostmortemStatus.DRAFT: frozenset({PostmortemStatus.IN_REVIEW}),
    PostmortemStatus.IN_REVIEW: frozenset({PostmortemStatus.DRAFT, PostmortemStatus.APPROVED}),
    PostmortemStatus.APPROVED: frozenset({PostmortemStatus.PUBLISHED}),
    PostmortemStatus.PUBLISHED: frozenset(),
}
"""Which lifecycle moves are legal.

**A published postmortem is a true dead end**, the same reasoning
Prompt 050's ``_ALLOWED_TRANSITIONS`` applied to a policy's lifecycle: a
document people already read and drew conclusions from does not get
silently rewritten. ``IN_REVIEW`` may still move back to ``DRAFT``,
because sending a postmortem back for more work before anyone outside
the review has seen it is exactly what review states exist for.
"""


class PostmortemService:
    """Postmortems: authoring, action items, review, approval, publication."""

    def __init__(
        self,
        postmortems: PostmortemRepository,
        action_items: ActionItemRepository,
        incidents: IncidentRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._postmortems = postmortems
        self._action_items = action_items
        self._incidents = incidents
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def start(
        self,
        organization_id: UUID,
        incident_id: UUID,
        *,
        author_id: str | None = None,
    ) -> Postmortem:
        """Begin a postmortem for one incident.

        Raises:
            ValidationError: If the incident has not yet resolved -- a
                postmortem written before the incident is over is
                documenting something still in motion.
            ConflictError: If one already exists for this incident.
        """
        stored = await self._incidents.require_in_org(organization_id, incident_id)
        if incident_status_of(stored.status) not in _CLOSED_INCIDENT_STATUSES:
            raise ValidationError(
                f"{stored.reference} is {stored.status!s}; a postmortem cannot begin until "
                "the incident has at least resolved."
            )
        if await self._postmortems.get_for_incident(organization_id, incident_id) is not None:
            raise ConflictError(f"A postmortem already exists for {stored.reference}.")

        return await self._postmortems.create(
            Postmortem(
                organization_id=organization_id,
                incident_id=incident_id,
                status=PostmortemStatus.DRAFT,
                author_id=author_id,
            )
        )

    async def update_content(
        self,
        organization_id: UUID,
        postmortem_id: UUID,
        *,
        executive_summary: str | None = None,
        timeline_summary: str | None = None,
        root_cause_summary: str | None = None,
        impact_summary: str | None = None,
        lessons_learned: str | None = None,
    ) -> Postmortem:
        """Edit a postmortem's content.

        Raises:
            ConflictError: If it has already been published.
        """
        row = await self._postmortems.require_in_org(organization_id, postmortem_id)
        if postmortem_status_of(row.status) is PostmortemStatus.PUBLISHED:
            raise ConflictError(f"Postmortem {postmortem_id} is published and cannot be edited.")
        if executive_summary is not None:
            row.executive_summary = executive_summary
        if timeline_summary is not None:
            row.timeline_summary = timeline_summary
        if root_cause_summary is not None:
            row.root_cause_summary = root_cause_summary
        if impact_summary is not None:
            row.impact_summary = impact_summary
        if lessons_learned is not None:
            row.lessons_learned = lessons_learned
        return await self._postmortems.update(row)

    async def add_action_item(
        self,
        organization_id: UUID,
        postmortem_id: UUID,
        *,
        title: str,
        description: str | None = None,
        owner_id: str | None = None,
        due_at: datetime | None = None,
    ) -> PostmortemActionItem:
        """Commit a follow-up action from a postmortem."""
        await self._postmortems.require_in_org(organization_id, postmortem_id)
        return await self._action_items.create(
            PostmortemActionItem(
                organization_id=organization_id,
                postmortem_id=postmortem_id,
                title=title,
                description=description,
                status=ActionItemStatus.OPEN,
                owner_id=owner_id,
                due_at=due_at,
            )
        )

    async def complete_action_item(
        self, organization_id: UUID, action_item_id: UUID, *, now: datetime | None = None
    ) -> PostmortemActionItem:
        """Mark an action item done."""
        row = await self._action_items.require_in_org(organization_id, action_item_id)
        row.status = ActionItemStatus.DONE
        row.completed_at = now or datetime.now(UTC)
        return await self._action_items.update(row)

    async def transition(
        self,
        organization_id: UUID,
        postmortem_id: UUID,
        *,
        target: PostmortemStatus,
        actor_id: str | None = None,
        now: datetime | None = None,
    ) -> Postmortem:
        """Move a postmortem through its lifecycle.

        Raises:
            ValidationError: If *target* is not reachable from the
                postmortem's current status, or approval is requested
                while action items remain unresolved with no owner --
                see the check below for why an unowned action item
                blocks approval specifically, not completion.
        """
        moment = now or datetime.now(UTC)
        row = await self._postmortems.require_in_org(organization_id, postmortem_id)
        current = postmortem_status_of(row.status)
        if target not in _ALLOWED_TRANSITIONS[current]:
            allowed = (
                ", ".join(sorted(str(one) for one in _ALLOWED_TRANSITIONS[current])) or "nothing"
            )
            raise ValidationError(
                f"A postmortem that is {current!s} cannot move to {target!s}. "
                f"Allowed from here: {allowed}."
            )

        if target is PostmortemStatus.APPROVED:
            items = await self._action_items.list_for_postmortem(organization_id, postmortem_id)
            unowned = [
                one
                for one in items
                if action_item_status_of(one.status) is not ActionItemStatus.CANCELLED
                and one.owner_id is None
            ]
            if unowned:
                raise ValidationError(
                    f"{len(unowned)} action item(s) have no owner. A commitment nobody owns "
                    "is not a commitment, and approval is where that gets caught."
                )
            row.approved_by = actor_id
            row.approved_at = moment

        if target is PostmortemStatus.PUBLISHED:
            row.published_at = moment

        row.status = target
        updated = await self._postmortems.update(row)

        if target is PostmortemStatus.PUBLISHED:
            await self._publish_event(
                PostmortemCompletedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "postmortem_id": str(postmortem_id),
                        "incident_id": str(row.incident_id),
                    },
                )
            )
        return updated

    async def get(self, organization_id: UUID, postmortem_id: UUID) -> Postmortem:
        """One postmortem.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._postmortems.require_in_org(organization_id, postmortem_id)

    async def get_for_incident(self, organization_id: UUID, incident_id: UUID) -> Postmortem | None:
        """The postmortem for one incident, if one has been started."""
        return await self._postmortems.get_for_incident(organization_id, incident_id)

    async def action_items(
        self, organization_id: UUID, postmortem_id: UUID
    ) -> list[PostmortemActionItem]:
        """Every action item committed in one postmortem."""
        await self._postmortems.require_in_org(organization_id, postmortem_id)
        return await self._action_items.list_for_postmortem(organization_id, postmortem_id)

    async def open_action_items_for(
        self, organization_id: UUID, owner_id: str
    ) -> list[PostmortemActionItem]:
        """One person's outstanding commitments across every postmortem."""
        return await self._action_items.list_open_for_owner(organization_id, owner_id)


__all__ = ["PostmortemService"]
