"""DeliveryService: the outgoing-delivery orchestrator -- this service's own core feature.

Against real PostgreSQL and a real, ASGI-backed fake receiving backend
(``tests/conftest.py``'s ``fake_backend_app``, served through
``httpx.ASGITransport``) -- every delivery in this file makes a genuine
HTTP request/response round trip. Nothing here mocks ``DeliveryService``
itself or its own collaborators (subscriptions, filters, transformations,
signatures, retry, endpoint health); only the network hop past the
service's own outbound HTTP client is substituted, exactly as
``tests/conftest.py``'s own module docstring describes.

One exception, isolated to its own class: :class:`TestDeliverConnectionFailure`
builds a second ``DeliveryService`` around a genuine, un-substituted
``httpx.AsyncClient`` (its default transport, real sockets) to exercise the
``httpx.HTTPError`` branch a fake ASGI backend structurally cannot produce.
See that class's own docstring for why the target has to be a real public
IP literal rather than loopback.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.delivery import WebhookDelivery
from app.models.endpoint import WebhookEndpoint
from app.models.enums import (
    DeliveryMode,
    DeliveryStatus,
    RetryBackoffStrategy,
    SecretStatus,
    SignatureAlgorithm,
    SubscriptionScope,
    TransformationKind,
)
from app.retry import engine as retry_engine
from app.services.delivery import DeliveryOutcome, DeliveryService, build_delivery_service
from app.signatures import engine as signatures_engine
from tests.conftest import FAKE_BACKEND_URL, HTTP_OK


async def _queue(
    delivery_service: DeliveryService,
    organization_id: uuid.UUID,
    make_endpoint,
    make_event,
    *,
    endpoint_overrides: dict[str, object] | None = None,
    event_overrides: dict[str, object] | None = None,
) -> tuple[WebhookDelivery, WebhookEndpoint]:
    """Register a fresh endpoint, raise a fresh event, and queue one delivery direct to it."""
    endpoint = await make_endpoint(**(endpoint_overrides or {}))
    event = await make_event(**(event_overrides or {}))
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    return delivery, endpoint


def _echoed_headers(attempt_response_body: str) -> dict[str, str]:
    """Lower-cased headers the fake backend's own ``/echo`` route saw."""
    echoed = json.loads(attempt_response_body)
    return {key.lower(): value for key, value in echoed["headers"].items()}


def _echoed_body(attempt_response_body: str) -> dict[str, object]:
    """The JSON payload the fake backend's own ``/echo`` route actually received."""
    echoed = json.loads(attempt_response_body)
    return dict(json.loads(echoed["body"]))


class TestFanOut:
    async def test_creates_one_delivery_per_matching_endpoint(
        self, delivery_service, make_endpoint, make_subscription, make_event, organization_id
    ) -> None:
        endpoint_a = await make_endpoint(name="a")
        endpoint_b = await make_endpoint(name="b")
        await make_subscription(endpoint_a.id, scope=SubscriptionScope.WILDCARD)
        await make_subscription(endpoint_b.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert {d.endpoint_id for d in deliveries} == {endpoint_a.id, endpoint_b.id}
        assert all(d.status == DeliveryStatus.QUEUED for d in deliveries)
        assert all(d.mode == DeliveryMode.QUEUED for d in deliveries)

    async def test_delivery_fields_are_copied_from_the_matching_event_and_endpoint(
        self, delivery_service, make_endpoint, make_subscription, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint(max_attempts=3)
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event(
            event_type="order.created", payload={"id": "abc"}, idempotency_key="idem-1"
        )

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert len(deliveries) == 1
        created = deliveries[0]
        assert created.event_id == event.id
        assert created.payload == {"id": "abc"}
        assert created.idempotency_key == "idem-1"
        assert created.max_attempts == 3
        assert created.subscription_id is not None

    async def test_max_attempts_defaults_to_eight_when_the_endpoint_has_none(
        self, delivery_service, make_endpoint, make_subscription, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert deliveries[0].max_attempts == 8

    async def test_skips_a_disabled_endpoint(
        self,
        delivery_service,
        endpoint_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await endpoint_service.update(organization_id, endpoint.id, enabled=False)
        event = await make_event()

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert deliveries == []

    async def test_skips_a_subscription_whose_filter_rejects_the_event(
        self,
        delivery_service,
        filter_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="only-critical",
            rules=[{"field": "severity", "operator": "eq", "value": "critical"}],
        )
        event = await make_event(severity="info")

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert deliveries == []

    async def test_a_passing_filter_still_lets_the_event_through(
        self,
        delivery_service,
        filter_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="only-critical",
            rules=[{"field": "severity", "operator": "eq", "value": "critical"}],
        )
        event = await make_event(severity="critical")

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert len(deliveries) == 1

    async def test_filter_rules_can_read_the_events_own_payload_via_metadata(
        self,
        delivery_service,
        filter_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        # `fan_out` maps `event.payload` onto the `"metadata"` filter
        # attribute -- confirms that wiring, not just the filter engine
        # itself (already covered at `FilterService` level).
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="only-high-priority",
            rules=[{"field": "metadata.priority", "operator": "eq", "value": "high"}],
        )
        event = await make_event(payload={"priority": "high"})

        deliveries = await delivery_service.fan_out(organization_id, event)

        assert len(deliveries) == 1

    async def test_schedules_each_queued_delivery_for_the_next_retry_sweep_tick(
        self,
        delivery_service,
        retry_queue_repo,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        # Without a `webhook_retry_queue` row, a freshly-queued delivery
        # would never be picked up by anything: `RetrySweepWorker` only
        # walks rows already in that table, and nothing else ever calls
        # `deliver()` for a delivery that has never yet been attempted.
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()
        before = datetime.now(UTC)

        [delivery] = await delivery_service.fan_out(organization_id, event)

        entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert entry is not None
        assert entry.next_attempt_at <= datetime.now(UTC)
        assert entry.next_attempt_at >= before - timedelta(seconds=1)


class TestQueueDirect:
    async def test_creates_exactly_one_delivery_bypassing_subscriptions(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint(max_attempts=2)
        event = await make_event()

        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        assert delivery.subscription_id is None
        assert delivery.mode == DeliveryMode.IMMEDIATE
        assert delivery.status == DeliveryStatus.QUEUED
        assert delivery.max_attempts == 2
        assert delivery.endpoint_id == endpoint.id

    async def test_schedules_the_delivery_for_the_next_retry_sweep_tick(
        self, delivery_service, retry_queue_repo, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        event = await make_event()

        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert entry is not None
        assert entry.next_attempt_at <= datetime.now(UTC)

    async def test_max_attempts_defaults_to_eight_when_the_endpoint_has_none(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        event = await make_event()

        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        assert delivery.max_attempts == 8


class TestDeliverSuccess:
    async def test_a_successful_delivery_is_marked_delivered_and_publishes_an_event(
        self, delivery_service, make_endpoint, make_event, organization_id, publisher
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )
        publisher.events.clear()  # drop the ingest-time `WebhookReceived`

        outcome = await delivery_service.deliver(organization_id, delivery)

        assert outcome.dead_lettered is False
        assert outcome.delivery.status == DeliveryStatus.DELIVERED
        assert outcome.delivery.delivered_at is not None
        assert outcome.attempt.status_code == HTTP_OK
        assert outcome.attempt.attempt_number == 1
        assert outcome.attempt.latency_ms is not None and outcome.attempt.latency_ms >= 0
        assert publisher.names == ["WebhookDelivered"]

    async def test_the_content_type_header_is_always_set_to_application_json(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert headers["content-type"] == "application/json"

    async def test_the_delivered_payload_matches_the_events_own_payload_when_untransformed(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            event_overrides={"payload": {"order_id": "o-1"}},
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        assert _echoed_body(outcome.attempt.response_body) == {"order_id": "o-1"}

    async def test_a_delivery_that_succeeds_after_a_prior_failure_clears_its_retry_queue_entry(
        self,
        delivery_service,
        endpoint_service,
        retry_queue_repo,
        make_endpoint,
        make_event,
        organization_id,
    ) -> None:
        delivery, endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )
        await delivery_service.deliver(organization_id, delivery)
        assert await retry_queue_repo.get_for_delivery(delivery.id) is not None

        await endpoint_service.update(organization_id, endpoint.id, url=f"{FAKE_BACKEND_URL}/echo")
        outcome = await delivery_service.deliver(organization_id, delivery)

        assert outcome.delivery.status == DeliveryStatus.DELIVERED
        assert await retry_queue_repo.get_for_delivery(delivery.id) is None


class TestDeliverTransformations:
    async def test_a_field_rename_rule_reshapes_the_delivered_payload(
        self, delivery_service, transformation_service, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="rename-id",
            kind=TransformationKind.FIELD_RENAME,
            config={"renames": [{"from": "old_field", "to": "new_field"}]},
        )
        event = await make_event(payload={"old_field": "value-123"})
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        assert _echoed_body(outcome.attempt.response_body) == {"new_field": "value-123"}

    async def test_two_header_mapping_rules_apply_in_priority_order(
        self, delivery_service, transformation_service, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="low-priority-applied-first",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Order": "first"}},
            priority=10,
        )
        await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="high-priority-applied-second",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Order": "second"}},
            priority=20,
        )
        event = await make_event()
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert headers["x-order"] == "second"

    async def test_a_rule_injected_header_survives_alongside_the_endpoints_own_static_header(
        self, delivery_service, transformation_service, make_endpoint, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint(headers={"X-Static": "endpoint-value"})
        await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="inject-header",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Injected": "rule-value"}},
        )
        event = await make_event()
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert headers["x-static"] == "endpoint-value"
        assert headers["x-injected"] == "rule-value"

    async def test_the_endpoints_own_static_header_wins_over_a_same_named_rule_header(
        self, delivery_service, transformation_service, make_endpoint, make_event, organization_id
    ) -> None:
        # `deliver()` applies `endpoint.headers` *after* the transformation
        # rules' own header mapping -- so on a name collision the
        # endpoint's own static value must be what actually crosses the
        # wire, not the rule's.
        endpoint = await make_endpoint(headers={"X-Priority": "endpoint-wins"})
        await transformation_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            name="collide",
            kind=TransformationKind.HEADER_MAPPING,
            config={"add": {"X-Priority": "rule-value"}},
        )
        event = await make_event()
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert headers["x-priority"] == "endpoint-wins"


class TestDeliverSigning:
    async def test_an_endpoint_with_no_active_secret_is_delivered_unsigned(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert "x-webhook-signature" not in headers

    async def test_a_signed_delivery_carries_a_verifiable_signature(
        self, delivery_service, make_endpoint, make_signature, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        event = await make_event(payload={"a": 1})
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        echoed = json.loads(outcome.attempt.response_body)
        headers = {k.lower(): v for k, v in echoed["headers"].items()}
        assert headers["x-webhook-signature-algorithm"] == SignatureAlgorithm.HMAC_SHA256.value
        assert "x-webhook-nonce" in headers
        assert "x-webhook-timestamp" in headers

        body_bytes = echoed["body"].encode("utf-8")
        signed_payload = (
            int(headers["x-webhook-timestamp"]).to_bytes(8, "big")
            + headers["x-webhook-nonce"].encode("utf-8")
            + body_bytes
        )
        expected_signature = signatures_engine.sign_payload(
            signed_payload, secret="shared-secret-value", algorithm=SignatureAlgorithm.HMAC_SHA256
        )
        assert headers["x-webhook-signature"] == expected_signature

    async def test_hmac_sha512_signing_is_supported_end_to_end(
        self, delivery_service, make_endpoint, make_signature, make_event, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(
            endpoint.id, secret="another-secret", algorithm=SignatureAlgorithm.HMAC_SHA512
        )
        event = await make_event()
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        echoed = json.loads(outcome.attempt.response_body)
        headers = {k.lower(): v for k, v in echoed["headers"].items()}
        assert headers["x-webhook-signature-algorithm"] == SignatureAlgorithm.HMAC_SHA512.value
        body_bytes = echoed["body"].encode("utf-8")
        signed_payload = (
            int(headers["x-webhook-timestamp"]).to_bytes(8, "big")
            + headers["x-webhook-nonce"].encode("utf-8")
            + body_bytes
        )
        expected_signature = signatures_engine.sign_payload(
            signed_payload, secret="another-secret", algorithm=SignatureAlgorithm.HMAC_SHA512
        )
        assert headers["x-webhook-signature"] == expected_signature

    async def test_a_rotating_but_not_active_secret_is_never_used_to_sign(
        self,
        delivery_service,
        signatures_repo,
        make_endpoint,
        make_signature,
        make_event,
        organization_id,
    ) -> None:
        # `active_secret_for` only ever returns an `ACTIVE` secret --
        # `ROTATING` exists purely so an inbound signature verified under
        # the previous secret still passes during the overlap window; it
        # must never be picked up to sign a *new* outbound delivery.
        endpoint = await make_endpoint()
        created = await make_signature(endpoint.id, secret="rotating-secret")
        created.status = SecretStatus.ROTATING
        await signatures_repo.update(created)
        event = await make_event()
        delivery = await delivery_service.queue_direct(
            organization_id, event, endpoint_id=endpoint.id
        )

        outcome = await delivery_service.deliver(organization_id, delivery)

        headers = _echoed_headers(outcome.attempt.response_body)
        assert "x-webhook-signature" not in headers


class TestDeliverRetryScheduling:
    async def test_a_failed_attempt_with_attempts_remaining_is_scheduled_for_retry(
        self,
        delivery_service,
        retry_queue_repo,
        make_endpoint,
        make_event,
        organization_id,
        publisher,
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )
        publisher.events.clear()  # drop the ingest-time `WebhookReceived`
        before = datetime.now(UTC)

        outcome = await delivery_service.deliver(organization_id, delivery)

        assert outcome.dead_lettered is False
        assert outcome.delivery.status == DeliveryStatus.RETRIED
        assert outcome.delivery.last_error == "HTTP 500"
        assert outcome.attempt.status_code == 500
        entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert entry is not None
        assert entry.attempt_number == 1
        assert entry.next_attempt_at > before
        assert entry.last_error == "HTTP 500"
        assert publisher.names == ["WebhookFailed", "WebhookRetried"]

    async def test_repeated_failures_reuse_the_same_retry_queue_row(
        self, delivery_service, retry_queue_repo, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )

        await delivery_service.deliver(organization_id, delivery)
        first_entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert first_entry is not None
        # Capture plain values now -- `retry_queue_repo` shares its session's
        # identity map with the rest of this test, so a second `deliver()`
        # call mutates this *same* ORM instance in place; holding onto
        # `first_entry` itself would silently observe the post-mutation
        # state too. The immutable `id`/`next_attempt_at` values do not.
        first_id, first_next_attempt_at = first_entry.id, first_entry.next_attempt_at

        await delivery_service.deliver(organization_id, delivery)
        second_entry = await retry_queue_repo.get_for_delivery(delivery.id)

        assert second_entry is not None
        assert second_entry.id == first_id
        assert second_entry.attempt_number == 2
        assert second_entry.next_attempt_at != first_next_attempt_at

    async def test_linear_backoff_delay_has_no_jitter(
        self,
        delivery_service,
        endpoint_service,
        retry_queue_repo,
        make_endpoint,
        make_event,
        organization_id,
    ) -> None:
        delivery, endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )
        await endpoint_service.update(
            organization_id, endpoint.id, backoff_strategy=RetryBackoffStrategy.LINEAR
        )
        before = datetime.now(UTC)

        await delivery_service.deliver(organization_id, delivery)

        entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert entry.backoff_strategy == RetryBackoffStrategy.LINEAR
        expected_delay = retry_engine.compute_linear_delay(1, base_seconds=5.0, max_seconds=3_600.0)
        actual_delay = (entry.next_attempt_at - before).total_seconds()
        assert expected_delay - 1.0 <= actual_delay <= expected_delay + 2.0

    async def test_exponential_backoff_delay_falls_within_its_own_jitter_bounds(
        self, delivery_service, retry_queue_repo, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )
        before = datetime.now(UTC)

        await delivery_service.deliver(organization_id, delivery)

        entry = await retry_queue_repo.get_for_delivery(delivery.id)
        assert entry.backoff_strategy == RetryBackoffStrategy.EXPONENTIAL
        actual_delay = (entry.next_attempt_at - before).total_seconds()
        # base_seconds=5.0, attempt=1 -> min(5 * 2**0, 3600) + uniform(0, 5) => [5, 10).
        assert 4.5 <= actual_delay <= 11.0


class TestDeliverDeadLettering:
    async def test_dead_letters_on_the_very_first_attempt_when_max_attempts_is_one(
        self,
        delivery_service,
        dead_letters_repo,
        retry_queue_repo,
        make_endpoint,
        make_event,
        organization_id,
        publisher,
    ) -> None:
        delivery, endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 1},
        )
        publisher.events.clear()  # drop the ingest-time `WebhookReceived`

        outcome = await delivery_service.deliver(organization_id, delivery)

        assert outcome.dead_lettered is True
        assert outcome.delivery.status == DeliveryStatus.EXPIRED
        rows = await dead_letters_repo.list_for_org(organization_id)
        assert len(rows) == 1
        assert rows[0].delivery_id == delivery.id
        assert rows[0].endpoint_id == endpoint.id
        assert rows[0].attempt_count == 1
        assert rows[0].last_error == "HTTP 500"
        assert await retry_queue_repo.get_for_delivery(delivery.id) is None
        # No `WebhookRetried` -- a dead-lettered delivery is never retried.
        assert publisher.names == ["WebhookFailed"]

    async def test_dead_letters_only_after_a_prior_retry_exhausts_the_attempt_budget(
        self,
        delivery_service,
        retry_queue_repo,
        make_endpoint,
        make_event,
        organization_id,
        publisher,
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 2},
        )
        publisher.events.clear()  # drop the ingest-time `WebhookReceived`

        first = await delivery_service.deliver(organization_id, delivery)
        assert first.dead_lettered is False
        assert first.delivery.status == DeliveryStatus.RETRIED
        assert await retry_queue_repo.get_for_delivery(delivery.id) is not None

        second = await delivery_service.deliver(organization_id, delivery)
        assert second.dead_lettered is True
        assert second.delivery.status == DeliveryStatus.EXPIRED
        # The dead-letter path clears whatever retry entry the prior
        # failure had queued.
        assert await retry_queue_repo.get_for_delivery(delivery.id) is None
        assert publisher.names == ["WebhookFailed", "WebhookRetried", "WebhookFailed"]


class TestDeliverConnectionFailure:
    """Exercises the ``except httpx.HTTPError`` branch with a genuine socket failure.

    ``fake_backend_app`` is served purely in-process through
    ``ASGITransport`` -- it structurally cannot produce a TCP-level
    failure (refused connection, timeout). Getting a real one means using
    a real ``httpx.AsyncClient`` with its default (network) transport, as
    ``api-gateway-service``'s own ``test_proxy_service.py`` does against
    ``127.0.0.1:1``.

    That trick alone does not carry over here: ``DeliveryService.deliver``
    re-validates the endpoint's URL for SSRF safety on every call, and
    loopback is rejected outright (see ``TestDeliverSsrfRevalidation``
    below for that path instead). A genuine connection failure therefore
    needs a real *public* IP literal -- ``1.1.1.1`` (Cloudflare, always
    publicly routable, never privately reassigned) on a port nothing
    there speaks HTTP on. Verified empirically against this environment:
    a direct connection to ``1.1.1.1:9`` with a short client timeout
    reliably raises ``httpx.ConnectTimeout`` in under two seconds --
    and the same holds with zero network egress at all, since a missing
    route also fails fast as ``httpx.ConnectError``. Either way it is a
    genuine ``httpx.HTTPError``, not a status code, so this is the only
    reliable way to reach that ``except`` clause without a real third
    -party server.
    """

    async def test_a_real_connection_failure_is_recorded_as_a_failed_attempt(
        self,
        deliveries_repo,
        attempts_repo,
        endpoints_repo,
        retry_queue_repo,
        dead_letters_repo,
        subscription_service,
        filter_service,
        transformation_service,
        signature_service,
        make_endpoint,
        make_event,
        organization_id,
        publisher,
    ) -> None:
        endpoint = await make_endpoint(url="http://1.1.1.1:9/", timeout_seconds=1.5)
        event = await make_event()

        real_client = httpx.AsyncClient()
        try:
            broken_service = DeliveryService(
                http_client=real_client,
                deliveries=deliveries_repo,
                attempts=attempts_repo,
                endpoints=endpoints_repo,
                retry_queue=retry_queue_repo,
                dead_letters=dead_letters_repo,
                subscriptions=subscription_service,
                filters=filter_service,
                transformations=transformation_service,
                signatures=signature_service,
                publish_event=publisher,
            )
            delivery = await broken_service.queue_direct(
                organization_id, event, endpoint_id=endpoint.id
            )
            publisher.events.clear()  # drop the ingest-time `WebhookReceived`
            outcome = await broken_service.deliver(organization_id, delivery)
        finally:
            await real_client.aclose()

        assert outcome.dead_lettered is False
        assert outcome.attempt.status_code is None
        assert outcome.attempt.error is not None
        assert outcome.delivery.status == DeliveryStatus.RETRIED
        assert outcome.delivery.last_error == outcome.attempt.error
        assert publisher.names == ["WebhookFailed", "WebhookRetried"]


class TestDeliverSsrfRevalidation:
    async def test_a_url_that_became_unsafe_after_registration_raises_and_touches_nothing(
        self,
        delivery_service,
        endpoints_repo,
        attempts_repo,
        make_endpoint,
        make_event,
        organization_id,
    ) -> None:
        # Simulates DNS rebinding (see `app/security/url_safety.py`'s own
        # docstring): the endpoint was safe when `make_endpoint`/
        # `EndpointService.register` validated it, but by delivery time
        # its `url` column has changed underneath -- written directly via
        # the repository, bypassing `EndpointService.update`'s own
        # `assert_safe_url` call, exactly as an out-of-band DNS change
        # would.
        delivery, endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )
        stored = await endpoints_repo.require_in_org(organization_id, endpoint.id)
        stored.url = "http://169.254.169.254/latest/meta-data"
        await endpoints_repo.update(stored)

        with pytest.raises(ValidationError):
            await delivery_service.deliver(organization_id, delivery)

        assert delivery.status == DeliveryStatus.QUEUED
        assert delivery.attempt_count == 0
        assert await attempts_repo.list_for_delivery(delivery.id) == []


class TestEndpointHealth:
    async def test_a_successful_delivery_leaves_a_fresh_endpoints_health_untouched_by_failure(
        self, delivery_service, endpoint_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )
        assert endpoint.consecutive_failures == 0

        await delivery_service.deliver(organization_id, delivery)

        refreshed = await endpoint_service.get(organization_id, endpoint.id)
        assert refreshed.consecutive_failures == 0
        assert refreshed.last_delivered_at is not None
        assert refreshed.last_failed_at is None

    async def test_a_failed_delivery_increments_consecutive_failures_and_a_later_success_resets_it(
        self, delivery_service, endpoint_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, endpoint = await _queue(
            delivery_service,
            organization_id,
            make_endpoint,
            make_event,
            endpoint_overrides={"url": f"{FAKE_BACKEND_URL}/error", "max_attempts": 5},
        )

        await delivery_service.deliver(organization_id, delivery)
        after_failure = await endpoint_service.get(organization_id, endpoint.id)
        assert after_failure.consecutive_failures == 1
        assert after_failure.last_failed_at is not None
        assert after_failure.last_delivered_at is None

        await endpoint_service.update(organization_id, endpoint.id, url=f"{FAKE_BACKEND_URL}/echo")
        await delivery_service.deliver(organization_id, delivery)

        after_success = await endpoint_service.get(organization_id, endpoint.id)
        assert after_success.consecutive_failures == 0
        assert after_success.last_delivered_at is not None


class TestGetAndListDeliveries:
    async def test_get_returns_the_delivery(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )

        found = await delivery_service.get(organization_id, delivery.id)

        assert found.id == delivery.id

    async def test_get_raises_not_found_for_an_unknown_id(
        self, delivery_service, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await delivery_service.get(organization_id, uuid.uuid4())

    async def test_get_raises_not_found_when_the_delivery_belongs_to_another_org(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery, _endpoint = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )

        with pytest.raises(NotFoundError):
            await delivery_service.get(uuid.uuid4(), delivery.id)

    async def test_list_deliveries_filters_by_status(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivered, _e1 = await _queue(delivery_service, organization_id, make_endpoint, make_event)
        await delivery_service.deliver(organization_id, delivered)
        still_queued, _e2 = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )

        rows = await delivery_service.list_deliveries(
            organization_id, status=DeliveryStatus.DELIVERED
        )

        assert [row.id for row in rows] == [delivered.id]
        assert still_queued.id not in [row.id for row in rows]

    async def test_list_deliveries_filters_by_endpoint_id(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        delivery_a, endpoint_a = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )
        delivery_b, endpoint_b = await _queue(
            delivery_service, organization_id, make_endpoint, make_event
        )
        assert endpoint_a.id != endpoint_b.id

        rows = await delivery_service.list_deliveries(organization_id, endpoint_id=endpoint_a.id)

        assert [row.id for row in rows] == [delivery_a.id]
        assert delivery_b.id not in [row.id for row in rows]

    async def test_list_deliveries_respects_limit(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        for _ in range(3):
            await _queue(delivery_service, organization_id, make_endpoint, make_event)

        rows = await delivery_service.list_deliveries(organization_id, limit=2)

        assert len(rows) == 2

    async def test_list_deliveries_is_tenant_scoped(
        self, delivery_service, make_endpoint, make_event, organization_id
    ) -> None:
        await _queue(delivery_service, organization_id, make_endpoint, make_event)

        rows = await delivery_service.list_deliveries(uuid.uuid4())

        assert rows == []


class TestBuildDeliveryService:
    async def test_builds_a_fully_wired_service_end_to_end(
        self,
        db_session,
        http_client,
        service_settings,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
        publisher,
    ) -> None:
        service = build_delivery_service(
            db_session,
            http_client,
            encryption_key=service_settings.secret_encryption_key,
            publish_event=publisher,
        )
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()

        deliveries = await service.fan_out(organization_id, event)
        assert len(deliveries) == 1
        publisher.events.clear()  # drop the ingest-time `WebhookReceived`

        outcome = await service.deliver(organization_id, deliveries[0])

        assert outcome.delivery.status == DeliveryStatus.DELIVERED
        assert publisher.names == ["WebhookDelivered"]

    async def test_a_service_built_without_a_publisher_does_not_raise(
        self,
        deliveries_repo,
        attempts_repo,
        endpoints_repo,
        retry_queue_repo,
        dead_letters_repo,
        subscription_service,
        filter_service,
        transformation_service,
        signature_service,
        http_client,
        make_endpoint,
        make_event,
        organization_id,
    ) -> None:
        service = DeliveryService(
            http_client=http_client,
            deliveries=deliveries_repo,
            attempts=attempts_repo,
            endpoints=endpoints_repo,
            retry_queue=retry_queue_repo,
            dead_letters=dead_letters_repo,
            subscriptions=subscription_service,
            filters=filter_service,
            transformations=transformation_service,
            signatures=signature_service,
            publish_event=None,
        )
        endpoint = await make_endpoint()
        event = await make_event()
        delivery = await service.queue_direct(organization_id, event, endpoint_id=endpoint.id)

        outcome: DeliveryOutcome = await service.deliver(organization_id, delivery)

        assert outcome.delivery.status == DeliveryStatus.DELIVERED
