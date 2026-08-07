"""FlowService: creation/lifecycle, and `_execute_step`'s own binding of the
engine's action steps to real sync/transform/event-routing/no-op collaborators.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
`app/flows/engine.py`'s own step-graph traversal (conditions, loops,
parallel fan-out, retries) is a separately, already-tested pure engine --
these tests build real flow *definitions* only to prove `FlowService`
wires each named action to the right collaborator and threads `context`
between steps correctly, never to re-verify the engine's own traversal.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import (
    EventRoutingStatus,
    FlowRunStatus,
    FlowStatus,
    FlowTrigger,
    TransformationKind,
)
from app.services.flow import FlowService

pytestmark = pytest.mark.asyncio


def _noop_definition() -> dict:
    return {"start": "s1", "steps": {"s1": {"kind": "action", "action": "noop", "next": None}}}


class TestCreate:
    async def test_create_starts_in_draft(self, flow_service: FlowService, organization_id) -> None:
        created = await flow_service.create(
            organization_id, name="My Flow", definition=_noop_definition()
        )
        assert created.status == FlowStatus.DRAFT
        assert created.enabled is False
        assert created.run_count == 0
        assert created.last_run_status == FlowRunStatus.NEVER_RUN
        assert created.last_run_at is None

    async def test_create_persists_the_definition_trigger_and_schedule(
        self, flow_service: FlowService, organization_id
    ) -> None:
        definition = _noop_definition()
        created = await flow_service.create(
            organization_id,
            name="Scheduled flow",
            definition=definition,
            trigger=FlowTrigger.SCHEDULED,
            schedule_interval_seconds=300,
        )
        assert created.definition == definition
        assert created.trigger == FlowTrigger.SCHEDULED
        assert created.schedule_interval_seconds == 300

    async def test_create_accepts_a_connector_id(
        self, flow_service: FlowService, organization_id, make_connector
    ) -> None:
        connector = await make_connector("owner-connector")
        created = await flow_service.create(
            organization_id,
            name="Owned flow",
            definition=_noop_definition(),
            connector_id=connector.id,
        )
        assert created.connector_id == connector.id


class TestGet:
    async def test_get_raises_not_found_for_a_missing_flow(
        self, flow_service: FlowService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await flow_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Org flow", definition=_noop_definition()
        )
        with pytest.raises(NotFoundError):
            await flow_service.get(uuid4(), created.id)


class TestListForOrg:
    async def test_list_finds_the_created_flow(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Listed flow", definition=_noop_definition()
        )
        found = await flow_service.list_for_org(organization_id)
        assert created.id in {f.id for f in found}

    async def test_list_filters_by_enabled(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Will activate", definition=_noop_definition()
        )
        await flow_service.activate(organization_id, created.id)

        enabled_only = await flow_service.list_for_org(organization_id, enabled=True)
        assert created.id in {f.id for f in enabled_only}

        disabled_only = await flow_service.list_for_org(organization_id, enabled=False)
        assert created.id not in {f.id for f in disabled_only}

    async def test_list_is_scoped_to_its_organization(
        self, flow_service: FlowService, organization_id
    ) -> None:
        await flow_service.create(organization_id, name="Mine", definition=_noop_definition())
        assert await flow_service.list_for_org(uuid4()) == []


class TestActivateDisable:
    async def test_activate_moves_to_active_and_enables(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="To activate", definition=_noop_definition()
        )
        activated = await flow_service.activate(organization_id, created.id)
        assert activated.status == FlowStatus.ACTIVE
        assert activated.enabled is True

    async def test_disable_moves_to_disabled_and_unenables(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="To disable", definition=_noop_definition()
        )
        await flow_service.activate(organization_id, created.id)
        disabled = await flow_service.disable(organization_id, created.id)
        assert disabled.status == FlowStatus.DISABLED
        assert disabled.enabled is False

    async def test_activate_raises_not_found_for_a_missing_flow(
        self, flow_service: FlowService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await flow_service.activate(organization_id, uuid4())

    async def test_disable_raises_not_found_for_a_missing_flow(
        self, flow_service: FlowService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await flow_service.disable(organization_id, uuid4())


class TestRunRequiresActive:
    async def test_run_raises_validation_error_when_flow_is_draft(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Draft flow", definition=_noop_definition()
        )
        with pytest.raises(ValidationError):
            await flow_service.run(organization_id, created, context={})

    async def test_run_raises_validation_error_when_flow_is_disabled(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Disabled flow", definition=_noop_definition()
        )
        await flow_service.activate(organization_id, created.id)
        disabled = await flow_service.disable(organization_id, created.id)
        with pytest.raises(ValidationError):
            await flow_service.run(organization_id, disabled, context={})

    async def test_run_failure_does_not_bump_run_count(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Draft flow", definition=_noop_definition()
        )
        with pytest.raises(ValidationError):
            await flow_service.run(organization_id, created, context={})
        assert created.run_count == 0


class TestExecuteStepBinding:
    """Direct unit coverage of `_execute_step`'s own action dispatch."""

    async def test_noop_returns_an_empty_dict(self, flow_service: FlowService) -> None:
        outcome = await flow_service._execute_step("noop", {}, {})
        assert outcome == {}

    async def test_unrecognised_action_raises_value_error(self, flow_service: FlowService) -> None:
        with pytest.raises(ValueError, match="bogus"):
            await flow_service._execute_step("bogus", {}, {})


class TestRunNoopFlow:
    async def test_run_succeeds_and_updates_flow_bookkeeping(
        self, flow_service: FlowService, organization_id, publisher
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Noop flow", definition=_noop_definition()
        )
        active = await flow_service.activate(organization_id, created.id)

        result = await flow_service.run(organization_id, active, context={})

        assert result.status == "succeeded"
        assert result.steps_executed == ["s1"]
        assert result.error is None

        assert active.run_count == 1
        assert active.last_run_status == FlowRunStatus.SUCCEEDED
        assert active.last_run_at is not None
        assert active.last_error is None
        assert "FlowExecuted" in publisher.names

    async def test_run_count_increments_on_every_run(
        self, flow_service: FlowService, organization_id
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Repeat flow", definition=_noop_definition()
        )
        active = await flow_service.activate(organization_id, created.id)
        await flow_service.run(organization_id, active, context={})
        await flow_service.run(organization_id, active, context={})
        assert active.run_count == 2

    async def test_published_event_carries_flow_id_and_status(
        self, flow_service: FlowService, organization_id, publisher
    ) -> None:
        created = await flow_service.create(
            organization_id, name="Event payload flow", definition=_noop_definition()
        )
        active = await flow_service.activate(organization_id, created.id)
        await flow_service.run(organization_id, active, context={})

        published = next(e for e in publisher.events if e.event_name == "FlowExecuted")
        assert published.payload["flow_id"] == str(active.id)
        assert published.payload["status"] == "succeeded"
        assert published.payload["steps"] == ["s1"]


class TestRunUnrecognisedActionThroughTheEngine:
    async def test_flow_run_reports_failed_status_and_records_the_error(
        self, flow_service: FlowService, organization_id
    ) -> None:
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "bogus", "next": None}},
        }
        created = await flow_service.create(
            organization_id, name="Bad action", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        result = await flow_service.run(organization_id, active, context={})

        assert result.status == "failed"
        assert result.error is not None
        assert "bogus" in result.error
        assert active.last_run_status == FlowRunStatus.FAILED
        assert active.last_error == result.error


class TestRunSyncAction:
    async def test_sync_step_creates_and_completes_a_real_sync_job(
        self, flow_service: FlowService, organization_id, make_connector, sync_jobs_repo
    ) -> None:
        connector = await make_connector("sync-target")
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "sync", "config": {}, "next": None}},
        }
        created = await flow_service.create(
            organization_id, name="Sync flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "records": [{"id": 1}, {"id": 2}],
        }
        result = await flow_service.run(organization_id, active, context=context)

        assert result.status == "succeeded"
        assert result.context["sync_status"] == "completed"

        jobs = await sync_jobs_repo.list_for_org(organization_id)
        assert len(jobs) == 1
        assert str(jobs[0].id) == result.context["sync_job_id"]
        assert jobs[0].connector_id == connector.id
        assert jobs[0].status == "completed"
        assert jobs[0].records_succeeded == 2

    async def test_sync_step_reads_connector_id_from_step_config(
        self, flow_service: FlowService, organization_id, make_connector, sync_jobs_repo
    ) -> None:
        connector = await make_connector("configured-target")
        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "sync",
                    "config": {"connector_id": str(connector.id)},
                    "next": None,
                }
            },
        }
        created = await flow_service.create(
            organization_id, name="Config-connector sync flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        result = await flow_service.run(
            organization_id,
            active,
            context={"organization_id": str(organization_id), "records": []},
        )

        assert result.status == "succeeded"
        jobs = await sync_jobs_repo.list_for_org(organization_id)
        assert jobs[0].connector_id == connector.id


class TestRunTransformAction:
    async def test_transform_step_applies_the_connectors_own_transformation_rules(
        self, flow_service: FlowService, transformation_service, organization_id, make_connector
    ) -> None:
        connector = await make_connector("transform-target")
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="rename-old-to-new",
            kind=TransformationKind.FIELD_MAPPING,
            config={"mapping": {"old_name": "new_name"}},
        )
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "transform", "config": {}, "next": None}},
        }
        created = await flow_service.create(
            organization_id, name="Transform flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "record": {"old_name": "bob"},
        }
        result = await flow_service.run(organization_id, active, context=context)

        assert result.status == "succeeded"
        assert result.context["record"] == {"new_name": "bob"}

    async def test_transform_step_with_no_rules_passes_the_record_through_unchanged(
        self, flow_service: FlowService, organization_id, make_connector
    ) -> None:
        connector = await make_connector("bare-target")
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "action", "action": "transform", "config": {}, "next": None}},
        }
        created = await flow_service.create(
            organization_id, name="Passthrough transform flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "record": {"unchanged": True},
        }
        result = await flow_service.run(organization_id, active, context=context)

        assert result.context["record"] == {"unchanged": True}


class TestRunRouteEventAction:
    async def test_route_event_step_persists_a_real_connector_event(
        self, flow_service: FlowService, organization_id, make_connector, events_repo
    ) -> None:
        connector = await make_connector("event-source")
        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "route_event",
                    "config": {"event_type": "flow.step.fired", "routes": []},
                    "next": None,
                }
            },
        }
        created = await flow_service.create(
            organization_id, name="Event flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "record": {"foo": "bar"},
        }
        result = await flow_service.run(organization_id, active, context=context)

        assert result.status == "succeeded"
        events = await events_repo.list_for_org(organization_id)
        assert len(events) == 1
        assert str(events[0].id) == result.context["event_id"]
        assert events[0].event_type == "flow.step.fired"
        assert events[0].payload == {"foo": "bar"}
        assert events[0].connector_id == connector.id
        assert events[0].routing_status == EventRoutingStatus.PENDING  # no routes declared

    async def test_route_event_step_with_a_matching_route_marks_it_routed(
        self, flow_service: FlowService, organization_id, make_connector, events_repo
    ) -> None:
        connector = await make_connector("event-source-routed")
        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "route_event",
                    "config": {
                        "event_type": "flow.step.fired",
                        "routes": [{"destination_kind": "webhook", "filter_rules": []}],
                    },
                    "next": None,
                }
            },
        }
        created = await flow_service.create(
            organization_id, name="Routed event flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "record": {"foo": "bar"},
        }
        await flow_service.run(organization_id, active, context=context)

        events = await events_repo.list_for_org(organization_id)
        assert events[0].routing_status == EventRoutingStatus.ROUTED
        assert events[0].routed_to == ["webhook"]

    async def test_route_event_step_without_a_connector_id_still_ingests(
        self, flow_service: FlowService, organization_id, events_repo
    ) -> None:
        definition = {
            "start": "s1",
            "steps": {
                "s1": {
                    "kind": "action",
                    "action": "route_event",
                    "config": {"event_type": "flow.no.connector", "routes": []},
                    "next": None,
                }
            },
        }
        created = await flow_service.create(
            organization_id, name="Connector-less event flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        result = await flow_service.run(
            organization_id,
            active,
            context={"organization_id": str(organization_id), "record": {"a": 1}},
        )

        assert result.status == "succeeded"
        events = await events_repo.list_for_org(organization_id)
        assert events[0].connector_id is None


class TestRunMixedSequence:
    async def test_transform_then_route_event_threads_context_between_steps(
        self,
        flow_service: FlowService,
        transformation_service,
        organization_id,
        make_connector,
        events_repo,
    ) -> None:
        connector = await make_connector("mixed-target")
        await transformation_service.create(
            organization_id,
            connector_id=connector.id,
            name="lowercase-name",
            kind=TransformationKind.NORMALIZATION,
            config={"rules": {"name": "lowercase"}},
        )
        definition = {
            "start": "s1",
            "steps": {
                "s1": {"kind": "action", "action": "transform", "config": {}, "next": "s2"},
                "s2": {
                    "kind": "action",
                    "action": "route_event",
                    "config": {"event_type": "flow.mixed", "routes": []},
                    "next": None,
                },
            },
        }
        created = await flow_service.create(
            organization_id, name="Mixed flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        context = {
            "organization_id": str(organization_id),
            "connector_id": str(connector.id),
            "record": {"name": "BOB"},
        }
        result = await flow_service.run(organization_id, active, context=context)

        assert result.status == "succeeded"
        assert result.steps_executed == ["s1", "s2"]
        assert result.context["record"] == {"name": "bob"}

        events = await events_repo.list_for_org(organization_id)
        assert len(events) == 1
        assert events[0].payload == {"name": "bob"}


class TestRunApprovalGate:
    async def test_approval_step_pauses_then_resumes_when_approved(
        self, flow_service: FlowService, organization_id
    ) -> None:
        definition = {
            "start": "s1",
            "steps": {
                "s1": {"kind": "approval", "next": "s2"},
                "s2": {"kind": "action", "action": "noop", "next": None},
            },
        }
        created = await flow_service.create(
            organization_id, name="Approval flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        awaiting = await flow_service.run(
            organization_id, active, context={"organization_id": str(organization_id)}
        )
        assert awaiting.status == "awaiting_approval"
        assert awaiting.awaiting_step == "s1"
        assert awaiting.steps_executed == ["s1"]
        assert active.run_count == 1
        assert active.last_run_status == FlowRunStatus.AWAITING_APPROVAL

        resumed = await flow_service.run(
            organization_id,
            active,
            context={"organization_id": str(organization_id), "_approved_s1": True},
        )
        assert resumed.status == "succeeded"
        assert resumed.steps_executed == ["s1", "s2"]
        assert active.run_count == 2
        assert active.last_run_status == FlowRunStatus.SUCCEEDED

    async def test_running_again_without_the_approval_flag_still_awaits(
        self, flow_service: FlowService, organization_id
    ) -> None:
        definition = {
            "start": "s1",
            "steps": {"s1": {"kind": "approval", "next": None}},
        }
        created = await flow_service.create(
            organization_id, name="Never approved flow", definition=definition
        )
        active = await flow_service.activate(organization_id, created.id)

        first = await flow_service.run(
            organization_id, active, context={"organization_id": str(organization_id)}
        )
        second = await flow_service.run(
            organization_id, active, context={"organization_id": str(organization_id)}
        )
        assert first.status == "awaiting_approval"
        assert second.status == "awaiting_approval"
        assert active.run_count == 2
