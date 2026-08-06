"""The five background workers, against real PostgreSQL and a real HTTP delivery target.

Each worker gets its own session in production; here that session
factory is the same SAVEPOINT-bound one every other fixture uses, so
data created through the service fixtures in the same test is visible
to the worker's own sessions -- see ``tests/conftest.py``'s
``db_session_factory``.

**Reading back what a worker's own session committed.** A worker
commits through a *new* ``AsyncSession`` object bound to the same
underlying connection, not the fixture's ``db_session``. A fresh query
for rows the fixture session never loaded (a list, a count, a
``require_in_org``) sees that commit immediately -- same connection,
same transaction. Re-reading an object the fixture session already
loaded into its own identity map does not: with ``expire_on_commit=
False`` that object is never refreshed just because another session on
the same connection committed. Those reads go through a brand-new
``db_session_factory()`` session instead, mirroring every prior
AI-IOS service's own ``test_workers.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import WebhookServiceSettings
from app.models.delivery import WebhookDeliveryAttempt
from app.models.enums import (
    DeliveryStatus,
    EventSource,
    IdempotencyStatus,
    ReplayScope,
    ReplayStatus,
    SecretStatus,
    SubscriptionScope,
)
from app.repositories.delivery import WebhookDeliveryAttemptRepository, WebhookDeliveryRepository
from app.repositories.governance import WebhookStatisticRepository
from app.repositories.idempotency import WebhookIdempotencyKeyRepository
from app.repositories.replay import WebhookReplayJobRepository
from app.repositories.retry import WebhookRetryQueueRepository
from app.repositories.signature import WebhookSignatureRepository
from app.services.delivery import DeliveryService
from app.services.endpoint import EndpointService
from app.services.event import EventService
from app.services.idempotency import IdempotencyService
from app.services.replay import ReplayService
from app.services.signature import SignatureService
from app.services.subscription import SubscriptionService
from app.workers.idempotency_sweep import IdempotencyExpirySweepWorker
from app.workers.replay_processor import ReplayProcessorWorker
from app.workers.retry_sweep import RetrySweepWorker
from app.workers.secret_expiry_sweep import SecretExpirySweepWorker
from app.workers.statistics_rollup import StatisticsRollupWorker
from tests.conftest import FAKE_BACKEND_URL, RecordingPublisher, ago, soon, utcnow

pytestmark = pytest.mark.asyncio


def _flaky_after(
    real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
) -> Callable[[], AsyncSession]:
    """A session factory that raises on its *fail_on_call*-th invocation only.

    Simulates one item's own session breaking mid-sweep without touching
    any other's -- these workers open one session per item by calling
    ``session_factory()`` with no arguments, so the only way to target
    "one item's session" from outside is by call order.
    """
    calls = {"n": 0}

    def factory() -> AsyncSession:
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise RuntimeError("Simulated per-item session failure.")
        return real_factory()

    return factory


async def _create_due_retry(
    endpoint_service: EndpointService,
    event_service: EventService,
    delivery_service: DeliveryService,
    retry_queue_repo: WebhookRetryQueueRepository,
    organization_id: uuid.UUID,
    *,
    max_attempts: int = 5,
    path: str = "/error",
):
    """Register an endpoint, deliver once (it fails against *path*), and force the
    resulting retry-queue entry due right now instead of waiting out its own backoff."""
    endpoint = await endpoint_service.register(
        organization_id,
        name=f"retry-target-{uuid.uuid4().hex[:8]}",
        url=f"{FAKE_BACKEND_URL}{path}",
        max_attempts=max_attempts,
    )
    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="retry.test", payload={}
    )
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    outcome = await delivery_service.deliver(organization_id, delivery)
    assert outcome.delivery.status == DeliveryStatus.RETRIED
    entry = await retry_queue_repo.get_for_delivery(delivery.id)
    assert entry is not None
    entry.next_attempt_at = ago(1)
    await retry_queue_repo.update(entry)
    return endpoint, delivery


async def _create_pending_replay_job(
    endpoint_service: EndpointService,
    subscription_service: SubscriptionService,
    event_service: EventService,
    replay_service: ReplayService,
    organization_id: uuid.UUID,
    *,
    dry_run: bool = False,
):
    endpoint = await endpoint_service.register(
        organization_id,
        name=f"replay-target-{uuid.uuid4().hex[:8]}",
        url=f"{FAKE_BACKEND_URL}/echo",
    )
    await subscription_service.create(
        organization_id, endpoint_id=endpoint.id, scope=SubscriptionScope.WILDCARD, event_types=[]
    )
    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="replay.test", payload={}
    )
    job = await replay_service.create(
        organization_id,
        scope=ReplayScope.BY_DATE_RANGE,
        date_range_start=ago(3_600),
        date_range_end=soon(3_600),
        dry_run=dry_run,
    )
    return endpoint, event, job


async def _seed_attempt(
    endpoint_service: EndpointService,
    event_service: EventService,
    delivery_service: DeliveryService,
    attempts_repo: WebhookDeliveryAttemptRepository,
    organization_id: uuid.UUID,
    *,
    status_code: int = 200,
    attempt_number: int = 1,
) -> WebhookDeliveryAttempt:
    endpoint = await endpoint_service.register(
        organization_id, name=f"stats-target-{uuid.uuid4().hex[:8]}", url=f"{FAKE_BACKEND_URL}/echo"
    )
    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="stats.test", payload={}
    )
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    return await attempts_repo.create(
        WebhookDeliveryAttempt(
            organization_id=organization_id,
            delivery_id=delivery.id,
            endpoint_id=endpoint.id,
            attempt_number=attempt_number,
            status_code=status_code,
            latency_ms=12.5,
            attempted_at=utcnow(),
        )
    )


class TestRetrySweepWorker:
    async def test_tick_retries_due_deliveries_across_organizations(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        retry_queue_repo: WebhookRetryQueueRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # `_due_deliveries` peeks unscoped across every organization,
        # then re-fetches each one tenant-scoped inside its own retry --
        # exercise that with two *different* organizations' own retries
        # due in the same tick.
        other_organization_id = uuid.uuid4()
        _, delivery_a = await _create_due_retry(
            endpoint_service, event_service, delivery_service, retry_queue_repo, organization_id
        )
        _, delivery_b = await _create_due_retry(
            endpoint_service,
            event_service,
            delivery_service,
            retry_queue_repo,
            other_organization_id,
        )

        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        attempted = await worker.tick()
        assert attempted == 2

        async with db_session_factory() as fresh:
            deliveries = WebhookDeliveryRepository(fresh)
            refreshed_a = await deliveries.require_in_org(organization_id, delivery_a.id)
            refreshed_b = await deliveries.require_in_org(other_organization_id, delivery_b.id)
            assert refreshed_a.attempt_count == 2
            assert refreshed_b.attempt_count == 2

    async def test_a_broken_endpoint_does_not_poison_the_rest(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        retry_queue_repo: WebhookRetryQueueRepository,
        organization_id: uuid.UUID,
    ) -> None:
        broken_endpoint, _broken_delivery = await _create_due_retry(
            endpoint_service, event_service, delivery_service, retry_queue_repo, organization_id
        )
        _, healthy_delivery = await _create_due_retry(
            endpoint_service, event_service, delivery_service, retry_queue_repo, organization_id
        )
        # A delivery whose own endpoint has since been deregistered: its
        # retry must fail cleanly rather than aborting the whole sweep.
        await endpoint_service.delete(organization_id, broken_endpoint.id)

        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        attempted = await worker.tick()
        assert attempted == 1

        async with db_session_factory() as fresh:
            refreshed_healthy = await WebhookDeliveryRepository(fresh).require_in_org(
                organization_id, healthy_delivery.id
            )
            assert refreshed_healthy.attempt_count == 2

    async def test_publishes_domain_events_through_each_retry(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        retry_queue_repo: WebhookRetryQueueRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await _create_due_retry(
            endpoint_service, event_service, delivery_service, retry_queue_repo, organization_id
        )
        worker_publisher = RecordingPublisher()
        worker = RetrySweepWorker(
            db_session_factory,
            http_client,
            encryption_key=service_settings.secret_encryption_key,
            publish_event=worker_publisher,
        )
        await worker.tick()
        assert "WebhookFailed" in worker_publisher.names
        assert "WebhookRetried" in worker_publisher.names

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        retry_queue_repo: WebhookRetryQueueRepository,
        organization_id: uuid.UUID,
    ) -> None:
        _, delivery = await _create_due_retry(
            endpoint_service, event_service, delivery_service, retry_queue_repo, organization_id
        )
        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await WebhookDeliveryRepository(fresh).require_in_org(
                organization_id, delivery.id
            )
            assert refreshed.attempt_count == 2

    async def test_a_tick_with_nothing_due_reports_zero(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
    ) -> None:
        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_a_retry_not_yet_due_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        retry_queue_repo: WebhookRetryQueueRepository,
        organization_id: uuid.UUID,
    ) -> None:
        endpoint = await endpoint_service.register(
            organization_id,
            name="not-due-endpoint",
            url=f"{FAKE_BACKEND_URL}/error",
            max_attempts=5,
        )
        event = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="retry.notdue", payload={}
        )
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )
        outcome = await delivery_service.deliver(organization_id, delivery)
        assert outcome.delivery.status == DeliveryStatus.RETRIED
        # Left with its own naturally-computed future `next_attempt_at`
        # -- unlike every other test in this class, nothing forces it due.

        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_a_freshly_queued_delivery_is_attempted_without_any_manual_deliver_call(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        organization_id: uuid.UUID,
    ) -> None:
        # Regression: `fan_out`/`queue_direct` alone used to leave a
        # delivery permanently `QUEUED` with zero attempts -- nothing
        # ever called `deliver()` for it, since the retry sweep only
        # walks rows already in `webhook_retry_queue`, and that row was
        # only ever created *after* a first attempt had already failed.
        endpoint = await endpoint_service.register(
            organization_id, name="never-manually-delivered", url=f"{FAKE_BACKEND_URL}/echo"
        )
        event = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="retry.autopickup", payload={}
        )
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )
        assert delivery.attempt_count == 0

        worker = RetrySweepWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        attempted = await worker.tick()

        assert attempted == 1
        async with db_session_factory() as fresh:
            refreshed = await WebhookDeliveryRepository(fresh).require_in_org(
                organization_id, delivery.id
            )
            assert refreshed.status == DeliveryStatus.DELIVERED
            assert refreshed.attempt_count == 1


class TestReplayProcessorWorker:
    async def test_tick_processes_every_pending_job(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        subscription_service: SubscriptionService,
        event_service: EventService,
        replay_service: ReplayService,
        organization_id: uuid.UUID,
    ) -> None:
        _, _, job = await _create_pending_replay_job(
            endpoint_service, subscription_service, event_service, replay_service, organization_id
        )

        worker = ReplayProcessorWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        processed = await worker.tick()
        assert processed == 1

        async with db_session_factory() as fresh:
            refreshed = await WebhookReplayJobRepository(fresh).require_in_org(
                organization_id, job.id
            )
            assert refreshed.status == ReplayStatus.COMPLETED
            assert refreshed.matched_count == 1
            assert refreshed.replayed_count == 1

            deliveries = await WebhookDeliveryRepository(fresh).list_for_org(organization_id)
            matching = [d for d in deliveries if d.replay_job_id == job.id]
            assert len(matching) == 1
            assert matching[0].status == DeliveryStatus.QUEUED

    async def test_dry_run_job_completes_without_creating_deliveries(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        subscription_service: SubscriptionService,
        event_service: EventService,
        replay_service: ReplayService,
        organization_id: uuid.UUID,
    ) -> None:
        _, _, job = await _create_pending_replay_job(
            endpoint_service,
            subscription_service,
            event_service,
            replay_service,
            organization_id,
            dry_run=True,
        )

        worker = ReplayProcessorWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        processed = await worker.tick()
        assert processed == 1

        async with db_session_factory() as fresh:
            refreshed = await WebhookReplayJobRepository(fresh).require_in_org(
                organization_id, job.id
            )
            assert refreshed.status == ReplayStatus.COMPLETED
            assert refreshed.matched_count == 1
            assert refreshed.replayed_count == 0
            assert refreshed.preview.get("event_ids")

            deliveries = await WebhookDeliveryRepository(fresh).list_for_org(organization_id)
            assert all(d.replay_job_id != job.id for d in deliveries)

    async def test_a_broken_items_session_does_not_poison_the_rest(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        subscription_service: SubscriptionService,
        event_service: EventService,
        replay_service: ReplayService,
        organization_id: uuid.UUID,
    ) -> None:
        # `_pending_jobs()` itself is call #1 and must succeed; a factory
        # that fails on the *first per-job* session (call #2) leaves the
        # second job's own run (call #3) unaffected.
        _, _, job_first = await _create_pending_replay_job(
            endpoint_service, subscription_service, event_service, replay_service, organization_id
        )
        _, _, job_second = await _create_pending_replay_job(
            endpoint_service, subscription_service, event_service, replay_service, organization_id
        )

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = ReplayProcessorWorker(
            flaky, http_client, encryption_key=service_settings.secret_encryption_key  # type: ignore[arg-type]
        )
        processed = await worker.tick()
        assert processed == 1

        async with db_session_factory() as fresh:
            jobs_repo = WebhookReplayJobRepository(fresh)
            refreshed_first = await jobs_repo.require_in_org(organization_id, job_first.id)
            refreshed_second = await jobs_repo.require_in_org(organization_id, job_second.id)
            statuses = {refreshed_first.status, refreshed_second.status}
            assert statuses == {ReplayStatus.PENDING, ReplayStatus.COMPLETED}

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
        endpoint_service: EndpointService,
        subscription_service: SubscriptionService,
        event_service: EventService,
        replay_service: ReplayService,
        organization_id: uuid.UUID,
    ) -> None:
        _, _, job = await _create_pending_replay_job(
            endpoint_service, subscription_service, event_service, replay_service, organization_id
        )
        worker = ReplayProcessorWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await WebhookReplayJobRepository(fresh).require_in_org(
                organization_id, job.id
            )
            assert refreshed.status == ReplayStatus.COMPLETED

    async def test_a_tick_with_nothing_pending_reports_zero(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        http_client: AsyncClient,
        service_settings: WebhookServiceSettings,
    ) -> None:
        worker = ReplayProcessorWorker(
            db_session_factory, http_client, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0


class TestStatisticsRollupWorker:
    async def test_tick_recomputes_every_organization_with_logged_attempts(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        attempts_repo: WebhookDeliveryAttemptRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_attempt(
            endpoint_service, event_service, delivery_service, attempts_repo, organization_id
        )

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        done = await worker.tick()
        assert done >= 1

        async with db_session_factory() as fresh:
            latest = await WebhookStatisticRepository(fresh).latest(organization_id)
            assert latest is not None
            assert latest.deliveries_attempted >= 1
            assert latest.deliveries_succeeded >= 1

    async def test_an_organization_with_deliveries_but_no_attempts_does_not_appear(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        organization_id: uuid.UUID,
    ) -> None:
        # `_organizations()` finds organizations via `SELECT DISTINCT
        # organization_id FROM webhook_delivery_attempts` -- an
        # organization with events/deliveries but zero *attempts* has
        # nothing to roll up, and correctly does not appear.
        endpoint = await endpoint_service.register(
            organization_id, name="no-attempts-endpoint", url=f"{FAKE_BACKEND_URL}/echo"
        )
        event = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="stats.none", payload={}
        )
        await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)

        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        attempts_repo: WebhookDeliveryAttemptRepository,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_attempt(
            endpoint_service, event_service, delivery_service, attempts_repo, organization_id
        )
        worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            latest = await WebhookStatisticRepository(fresh).latest(organization_id)
            assert latest is not None

    async def test_a_failure_recomputing_one_organization_does_not_poison_the_next(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        endpoint_service: EndpointService,
        event_service: EventService,
        delivery_service: DeliveryService,
        attempts_repo: WebhookDeliveryAttemptRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # `_organizations()` itself is call #1 and must succeed; a
        # factory that fails on the *first per-organization* recompute
        # (call #2) leaves the second organization's own recompute
        # (call #3) unaffected -- regardless of which organization the
        # database happens to return first.
        other_organization_id = uuid.uuid4()
        await _seed_attempt(
            endpoint_service, event_service, delivery_service, attempts_repo, organization_id
        )
        await _seed_attempt(
            endpoint_service, event_service, delivery_service, attempts_repo, other_organization_id
        )

        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = StatisticsRollupWorker(flaky, window_seconds=3_600)  # type: ignore[arg-type]
        done = await worker.tick()
        assert done == 1


class TestIdempotencyExpirySweepWorker:
    async def test_tick_expires_every_due_key(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        idempotency_service: IdempotencyService,
        idempotency_repo: WebhookIdempotencyKeyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        reserved = await idempotency_service.reserve(organization_id, "idem-key-due")
        reserved.expires_at = ago(1)
        await idempotency_repo.update(reserved)

        worker = IdempotencyExpirySweepWorker(db_session_factory)
        expired = await worker.tick()
        assert expired >= 1

        async with db_session_factory() as fresh:
            refreshed = await WebhookIdempotencyKeyRepository(fresh).get_by_key(
                organization_id, "idem-key-due"
            )
            assert refreshed is not None
            assert refreshed.status == IdempotencyStatus.EXPIRED

    async def test_a_key_not_yet_due_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        idempotency_service: IdempotencyService,
        organization_id: uuid.UUID,
    ) -> None:
        await idempotency_service.reserve(organization_id, "idem-key-future")
        worker = IdempotencyExpirySweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_a_tick_with_nothing_due_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = IdempotencyExpirySweepWorker(db_session_factory)
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        idempotency_service: IdempotencyService,
        idempotency_repo: WebhookIdempotencyKeyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        reserved = await idempotency_service.reserve(organization_id, "idem-key-run-job")
        reserved.expires_at = ago(1)
        await idempotency_repo.update(reserved)

        worker = IdempotencyExpirySweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await WebhookIdempotencyKeyRepository(fresh).get_by_key(
                organization_id, "idem-key-run-job"
            )
            assert refreshed is not None
            assert refreshed.status == IdempotencyStatus.EXPIRED

    async def test_a_totally_broken_session_factory_is_swallowed_for_the_whole_tick(self) -> None:
        # This worker wraps its *entire* tick body in one try/except --
        # a session that cannot even open must not crash the sweep.
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = IdempotencyExpirySweepWorker(_broken)  # type: ignore[arg-type]
        assert await worker.tick() == 0


class TestSecretExpirySweepWorker:
    async def test_tick_expires_every_due_rotating_secret(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: WebhookServiceSettings,
        make_endpoint,
        make_signature,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="v1-secret")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="v2-secret"
        )

        rows = await signatures_repo.list_usable_for_endpoint(endpoint.id)
        rotating = next(row for row in rows if row.status == SecretStatus.ROTATING)
        rotating.expires_at = ago(1)
        await signatures_repo.update(rotating)

        worker = SecretExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        expired = await worker.tick()
        assert expired >= 1

        async with db_session_factory() as fresh:
            refreshed = await WebhookSignatureRepository(fresh).require_in_org(
                organization_id, rotating.id
            )
            assert refreshed.status == SecretStatus.EXPIRED

    async def test_a_secret_not_yet_due_is_left_alone(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: WebhookServiceSettings,
        make_endpoint,
        make_signature,
        signature_service: SignatureService,
        organization_id: uuid.UUID,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="v1-secret")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="v2-secret"
        )
        # Left with its own naturally-computed overlap window (24h out).

        worker = SecretExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_a_tick_with_nothing_due_reports_zero(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: WebhookServiceSettings,
    ) -> None:
        worker = SecretExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        assert await worker.tick() == 0

    async def test_run_job_delegates_to_tick(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        service_settings: WebhookServiceSettings,
        make_endpoint,
        make_signature,
        signature_service: SignatureService,
        signatures_repo: WebhookSignatureRepository,
        organization_id: uuid.UUID,
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="v1-secret")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="v2-secret"
        )
        rows = await signatures_repo.list_usable_for_endpoint(endpoint.id)
        rotating = next(row for row in rows if row.status == SecretStatus.ROTATING)
        rotating.expires_at = ago(1)
        await signatures_repo.update(rotating)

        worker = SecretExpirySweepWorker(
            db_session_factory, encryption_key=service_settings.secret_encryption_key
        )
        await worker.run_job(None)  # type: ignore[arg-type]

        async with db_session_factory() as fresh:
            refreshed = await WebhookSignatureRepository(fresh).require_in_org(
                organization_id, rotating.id
            )
            assert refreshed.status == SecretStatus.EXPIRED

    async def test_a_totally_broken_session_factory_is_swallowed_for_the_whole_tick(self) -> None:
        # This worker wraps its *entire* tick body in one try/except --
        # a session that cannot even open must not crash the sweep.
        def _broken() -> AsyncSession:
            raise RuntimeError("Simulated session failure.")

        worker = SecretExpirySweepWorker(_broken, encryption_key="unused")  # type: ignore[arg-type]
        assert await worker.tick() == 0
