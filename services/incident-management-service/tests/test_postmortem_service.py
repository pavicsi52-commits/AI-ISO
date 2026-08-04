"""PostmortemService: authoring, action items, review, approval, publication."""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ActionItemStatus, IncidentStatus, PostmortemStatus
from app.services.incident import IncidentService
from app.services.postmortem import PostmortemService

pytestmark = pytest.mark.asyncio


async def _resolve(incident_service: IncidentService, organization_id, incident_id) -> None:
    await incident_service.transition(organization_id, incident_id, target=IncidentStatus.ASSIGNED)
    await incident_service.transition(
        organization_id, incident_id, target=IncidentStatus.ACKNOWLEDGED
    )
    await incident_service.transition(
        organization_id, incident_id, target=IncidentStatus.INVESTIGATING
    )
    await incident_service.transition(organization_id, incident_id, target=IncidentStatus.RESOLVED)


class TestStart:
    async def test_starting_before_resolution_raises(
        self, postmortem_service: PostmortemService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        with pytest.raises(ValidationError):
            await postmortem_service.start(organization_id, incident.id)

    async def test_starting_after_resolution_succeeds(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id, author_id="alice")
        assert created.status == PostmortemStatus.DRAFT
        assert created.author_id == "alice"

    async def test_starting_a_second_postmortem_for_the_same_incident_raises(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        await postmortem_service.start(organization_id, incident.id)
        with pytest.raises(ConflictError):
            await postmortem_service.start(organization_id, incident.id)


class TestUpdateContent:
    async def test_update_content_writes_fields(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        updated = await postmortem_service.update_content(
            organization_id, created.id, executive_summary="A summary."
        )
        assert updated.executive_summary == "A summary."

    async def test_update_content_on_a_published_postmortem_raises(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.APPROVED
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.PUBLISHED
        )
        with pytest.raises(ConflictError):
            await postmortem_service.update_content(
                organization_id, created.id, executive_summary="Too late."
            )


class TestActionItems:
    async def test_add_action_item_defaults_to_open(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        item = await postmortem_service.add_action_item(
            organization_id, created.id, title="Add alert"
        )
        assert item.status == ActionItemStatus.OPEN

    async def test_complete_action_item_marks_it_done(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        item = await postmortem_service.add_action_item(
            organization_id, created.id, title="Add alert"
        )
        done = await postmortem_service.complete_action_item(organization_id, item.id)
        assert done.status == ActionItemStatus.DONE
        assert done.completed_at is not None

    async def test_action_items_lists_everything_committed(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.add_action_item(organization_id, created.id, title="A")
        await postmortem_service.add_action_item(organization_id, created.id, title="B")
        items = await postmortem_service.action_items(organization_id, created.id)
        assert len(items) == 2


class TestTransition:
    async def test_illegal_transition_raises(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        with pytest.raises(ValidationError):
            await postmortem_service.transition(
                organization_id, created.id, target=PostmortemStatus.PUBLISHED
            )

    async def test_approval_refuses_while_an_action_item_has_no_owner(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.add_action_item(organization_id, created.id, title="Unowned")
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        with pytest.raises(ValidationError):
            await postmortem_service.transition(
                organization_id, created.id, target=PostmortemStatus.APPROVED
            )

    async def test_approval_succeeds_once_every_action_item_is_owned(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.add_action_item(
            organization_id, created.id, title="Owned", owner_id="alice"
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        approved = await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.APPROVED, actor_id="bob"
        )
        assert approved.status == PostmortemStatus.APPROVED
        assert approved.approved_by == "bob"

    async def test_publishing_sets_published_at_and_publishes_an_event(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
        publisher,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.APPROVED
        )
        published = await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.PUBLISHED
        )
        assert published.published_at is not None
        assert "PostmortemCompleted" in publisher.names

    async def test_in_review_may_move_back_to_draft(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        back = await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.DRAFT
        )
        assert back.status == PostmortemStatus.DRAFT

    async def test_published_is_a_true_dead_end(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.IN_REVIEW
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.APPROVED
        )
        await postmortem_service.transition(
            organization_id, created.id, target=PostmortemStatus.PUBLISHED
        )
        with pytest.raises(ValidationError):
            await postmortem_service.transition(
                organization_id, created.id, target=PostmortemStatus.DRAFT
            )


class TestGetters:
    async def test_get_for_incident_returns_none_before_starting(
        self, postmortem_service: PostmortemService, organization_id, make_incident
    ) -> None:
        incident = await make_incident()
        found = await postmortem_service.get_for_incident(organization_id, incident.id)
        assert found is None

    async def test_open_action_items_for_owner_finds_open_and_in_progress(
        self,
        postmortem_service: PostmortemService,
        incident_service: IncidentService,
        organization_id,
        make_incident,
    ) -> None:
        incident = await make_incident()
        await _resolve(incident_service, organization_id, incident.id)
        created = await postmortem_service.start(organization_id, incident.id)
        await postmortem_service.add_action_item(
            organization_id, created.id, title="Mine", owner_id="alice"
        )
        found = await postmortem_service.open_action_items_for(organization_id, "alice")
        assert len(found) == 1
