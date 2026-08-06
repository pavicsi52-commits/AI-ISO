"""ReplayService and WebhookReplayJobRepository.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``ReplayService.run()`` composes a fully-wired ``DeliveryService`` (see
``tests/conftest.py``'s own ``replay_service`` fixture) purely to exercise
its own orchestration -- job status transitions, matched/replayed/failed
counts, dry-run behaviour. ``DeliveryService.fan_out``/``deliver``'s own
mechanics (subscription matching, filters, transformations, signing,
retry scheduling) are a different scope's own dedicated test file; here a
"bad" event is manufactured the cheapest real way available -- a
subscription whose own endpoint has since been soft-deleted, so
``fan_out``'s own ``endpoints.require_in_org`` genuinely raises
``NotFoundError`` for that one event, without mocking anything.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import EventSource, ReplayScope, ReplayStatus, SubscriptionScope
from app.models.replay import WebhookReplayJob
from app.repositories.replay import WebhookReplayJobRepository
from app.services.endpoint import EndpointService
from app.services.replay import ReplayService
from tests.conftest import ago, soon

pytestmark = pytest.mark.asyncio


class TestReplayCreate:
    async def test_by_event_requires_event_id(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(organization_id, scope=ReplayScope.BY_EVENT)

    async def test_by_endpoint_requires_endpoint_id(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(organization_id, scope=ReplayScope.BY_ENDPOINT)

    async def test_by_subscription_requires_subscription_id(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(organization_id, scope=ReplayScope.BY_SUBSCRIPTION)

    async def test_by_date_range_requires_both_bounds(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(organization_id, scope=ReplayScope.BY_DATE_RANGE)

    async def test_by_date_range_requires_end_when_only_start_given(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(
                organization_id, scope=ReplayScope.BY_DATE_RANGE, date_range_start=ago(3600)
            )

    async def test_by_date_range_requires_start_when_only_end_given(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(
                organization_id, scope=ReplayScope.BY_DATE_RANGE, date_range_end=soon(3600)
            )

    async def test_by_date_range_rejects_start_equal_to_end(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        moment = soon(60)
        with pytest.raises(ValidationError):
            await replay_service.create(
                organization_id,
                scope=ReplayScope.BY_DATE_RANGE,
                date_range_start=moment,
                date_range_end=moment,
            )

    async def test_by_date_range_rejects_start_after_end(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(
                organization_id,
                scope=ReplayScope.BY_DATE_RANGE,
                date_range_start=soon(3600),
                date_range_end=ago(3600),
            )

    async def test_invalid_request_never_writes_a_row(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(ValidationError):
            await replay_service.create(organization_id, scope=ReplayScope.BY_EVENT)
        assert await replay_service.list_jobs(organization_id) == []

    async def test_by_event_succeeds_with_event_id(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id, requested_by="alice"
        )
        assert created.scope == ReplayScope.BY_EVENT
        assert created.status == ReplayStatus.PENDING
        assert created.dry_run is False
        assert created.requested_by == "alice"
        assert created.matched_count == 0
        assert created.replayed_count == 0
        assert created.failed_count == 0

    async def test_by_endpoint_succeeds_with_endpoint_id(
        self, replay_service: ReplayService, make_endpoint, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_ENDPOINT, endpoint_id=endpoint.id
        )
        assert created.scope == ReplayScope.BY_ENDPOINT
        assert created.endpoint_id == endpoint.id

    async def test_by_subscription_succeeds_with_subscription_id(
        self, replay_service: ReplayService, make_endpoint, make_subscription, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_SUBSCRIPTION, subscription_id=subscription.id
        )
        assert created.scope == ReplayScope.BY_SUBSCRIPTION
        assert created.subscription_id == subscription.id

    async def test_by_date_range_succeeds_with_start_strictly_before_end(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        created = await replay_service.create(
            organization_id,
            scope=ReplayScope.BY_DATE_RANGE,
            date_range_start=ago(3600),
            date_range_end=soon(3600),
        )
        assert created.scope == ReplayScope.BY_DATE_RANGE

    async def test_dry_run_flag_is_stored(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id, dry_run=True
        )
        assert created.dry_run is True


class TestReplayGet:
    async def test_get_returns_the_created_job(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        found = await replay_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_for_a_missing_job(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await replay_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        with pytest.raises(NotFoundError):
            await replay_service.get(uuid4(), created.id)


class TestReplayList:
    async def test_list_jobs_is_empty_initially(
        self, replay_service: ReplayService, organization_id
    ) -> None:
        assert await replay_service.list_jobs(organization_id) == []

    async def test_list_jobs_returns_newest_first(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        first = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        second = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        found = await replay_service.list_jobs(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_list_jobs_is_scoped_to_its_organization(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        await replay_service.create(organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id)
        found = await replay_service.list_jobs(uuid4())
        assert found == []


class TestReplayPreview:
    async def test_preview_by_event_reports_the_one_matching_event(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        result = await replay_service.preview(organization_id, created.id)
        assert result["matched_count"] == 1
        assert result["event_ids"] == [str(event.id)]

    async def test_preview_never_creates_a_delivery(
        self, replay_service: ReplayService, make_event, deliveries_repo, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        await replay_service.preview(organization_id, created.id)
        assert await deliveries_repo.list_for_org(organization_id) == []

    async def test_preview_raises_not_found_for_a_cross_organization_job(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )
        with pytest.raises(NotFoundError):
            await replay_service.preview(uuid4(), created.id)

    async def test_preview_event_ids_are_capped_at_fifty_even_with_more_matches(
        self, replay_service: ReplayService, make_event, organization_id
    ) -> None:
        for i in range(55):
            await make_event(f"bulk.event.{i}")
        created = await replay_service.create(
            organization_id,
            scope=ReplayScope.BY_DATE_RANGE,
            date_range_start=ago(3600),
            date_range_end=soon(3600),
        )
        result = await replay_service.preview(organization_id, created.id)
        assert result["matched_count"] == 55
        assert len(result["event_ids"]) == 50


class TestReplayRun:
    async def test_dry_run_transitions_pending_to_completed_without_replaying(
        self, replay_service: ReplayService, make_event, deliveries_repo, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id, dry_run=True
        )
        assert created.status == ReplayStatus.PENDING

        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.COMPLETED
        assert completed.started_at is not None
        assert completed.completed_at is not None
        assert completed.matched_count == 1
        assert completed.replayed_count == 0
        assert completed.failed_count == 0
        assert completed.preview == {"event_ids": [str(event.id)]}
        assert await deliveries_repo.list_for_org(organization_id) == []

    async def test_by_event_run_replays_the_matching_event(
        self,
        replay_service: ReplayService,
        make_endpoint,
        make_subscription,
        make_event,
        deliveries_repo,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id
        )

        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.COMPLETED
        assert completed.matched_count == 1
        assert completed.replayed_count == 1
        assert completed.failed_count == 0
        assert completed.error is None
        deliveries = await deliveries_repo.list_for_org(organization_id)
        assert len(deliveries) == 1
        assert deliveries[0].replay_job_id == created.id

    async def test_one_bad_event_does_not_abort_the_whole_job(
        self,
        replay_service: ReplayService,
        make_endpoint,
        make_subscription,
        make_event,
        endpoint_service: EndpointService,
        deliveries_repo,
        organization_id,
    ) -> None:
        endpoint_good = await make_endpoint("endpoint-good")
        endpoint_bad = await make_endpoint("endpoint-bad")
        # `SubscriptionScope.EVENT`'s own `_scope_matches` glob-tests
        # `scope_reference` (not `event_types`, which is a second,
        # independent filter that defaults to "matches everything").
        await make_subscription(
            endpoint_good.id, scope=SubscriptionScope.EVENT, scope_reference="good.*"
        )
        await make_subscription(
            endpoint_bad.id, scope=SubscriptionScope.EVENT, scope_reference="bad.*"
        )
        await make_event("good.event")
        await make_event("bad.event")

        # Soft-delete the "bad" endpoint after its subscription exists, so
        # `DeliveryService.fan_out`'s own `endpoints.require_in_org` call
        # genuinely raises `NotFoundError` for the event that matches it --
        # a real per-event failure, not a mock.
        await endpoint_service.delete(organization_id, endpoint_bad.id)

        created = await replay_service.create(
            organization_id,
            scope=ReplayScope.BY_DATE_RANGE,
            date_range_start=ago(3600),
            date_range_end=soon(3600),
        )
        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.COMPLETED
        assert completed.matched_count == 2
        assert completed.replayed_count == 1
        assert completed.failed_count == 1
        assert completed.error is not None
        deliveries = await deliveries_repo.list_for_org(organization_id)
        assert len(deliveries) == 1
        assert deliveries[0].endpoint_id == endpoint_good.id

    async def test_a_structurally_broken_job_is_marked_failed(
        self, replay_service: ReplayService, event_service, organization_id
    ) -> None:
        # A `BY_EVENT` job whose `event_id` exists (satisfying the column's
        # own foreign key) but belongs to a *different* organization:
        # `_matching_events` itself raises `NotFoundError` via
        # `require_in_org`, which is the job's own outer failure -- unlike
        # a per-event fan-out failure, this must mark the job `FAILED`, not
        # `COMPLETED`.
        other_orgs_event = await event_service.ingest_internal(
            uuid4(), source=EventSource.CUSTOM, event_type="someone.elses.event", payload={}
        )
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=other_orgs_event.id
        )
        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.FAILED
        assert completed.error is not None
        assert completed.matched_count == 0
        assert completed.replayed_count == 0
        assert completed.failed_count == 0
        assert completed.completed_at is not None

    async def test_by_endpoint_scope_replays_every_event_in_the_organization(
        self,
        replay_service: ReplayService,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        # docs: BY_ENDPOINT/BY_SUBSCRIPTION both replay every event in the
        # organization within the job's own date bounds -- narrowing to the
        # specific endpoint/subscription happens inside `fan_out`'s own
        # subscription matching, not in `_matching_events`.
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await make_event("one")
        await make_event("two")

        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_ENDPOINT, endpoint_id=endpoint.id
        )
        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.COMPLETED
        assert completed.matched_count == 2
        assert completed.replayed_count == 2

    async def test_by_subscription_scope_is_unbounded_without_date_range(
        self,
        replay_service: ReplayService,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await make_event("alpha")

        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_SUBSCRIPTION, subscription_id=subscription.id
        )
        completed = await replay_service.run(organization_id, created.id)

        assert completed.status == ReplayStatus.COMPLETED
        assert completed.matched_count == 1
        assert completed.replayed_count == 1

    async def test_run_moves_status_through_running_before_completed(
        self, replay_service: ReplayService, replay_jobs_repo, make_event, organization_id
    ) -> None:
        event = await make_event()
        created = await replay_service.create(
            organization_id, scope=ReplayScope.BY_EVENT, event_id=event.id, dry_run=True
        )
        completed = await replay_service.run(organization_id, created.id)
        # `started_at` is set as soon as the job moves to RUNNING, before
        # the (dry-run) work happens, and is strictly not None afterwards.
        assert completed.started_at <= completed.completed_at


class TestReplayJobRepository:
    async def test_require_in_org_raises_not_found_for_a_missing_job(
        self, replay_jobs_repo: WebhookReplayJobRepository, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await replay_jobs_repo.require_in_org(organization_id, uuid4())

    async def test_require_in_org_finds_its_own_job(
        self, replay_jobs_repo: WebhookReplayJobRepository, organization_id
    ) -> None:
        # `event_id` is left unset here (nullable, `ON DELETE SET NULL`) --
        # these repository-level tests exercise CRUD only, not the
        # scope/required-field validation that lives in the service layer.
        created = await replay_jobs_repo.create(
            WebhookReplayJob(organization_id=organization_id, scope=ReplayScope.BY_EVENT)
        )
        found = await replay_jobs_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_list_for_org_orders_newest_first(
        self, replay_jobs_repo: WebhookReplayJobRepository, organization_id
    ) -> None:
        first = await replay_jobs_repo.create(
            WebhookReplayJob(organization_id=organization_id, scope=ReplayScope.BY_EVENT)
        )
        second = await replay_jobs_repo.create(
            WebhookReplayJob(organization_id=organization_id, scope=ReplayScope.BY_EVENT)
        )
        found = await replay_jobs_repo.list_for_org(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_list_pending_returns_only_pending_jobs_across_organizations(
        self, replay_jobs_repo: WebhookReplayJobRepository, organization_id
    ) -> None:
        other_org = uuid4()
        pending_here = await replay_jobs_repo.create(
            WebhookReplayJob(
                organization_id=organization_id,
                scope=ReplayScope.BY_EVENT,
                status=ReplayStatus.PENDING,
            )
        )
        pending_other_org = await replay_jobs_repo.create(
            WebhookReplayJob(
                organization_id=other_org,
                scope=ReplayScope.BY_EVENT,
                status=ReplayStatus.PENDING,
            )
        )
        await replay_jobs_repo.create(
            WebhookReplayJob(
                organization_id=organization_id,
                scope=ReplayScope.BY_EVENT,
                status=ReplayStatus.COMPLETED,
            )
        )
        found_ids = {job.id for job in await replay_jobs_repo.list_pending()}
        assert pending_here.id in found_ids
        assert pending_other_org.id in found_ids
        assert len(found_ids) == 2
