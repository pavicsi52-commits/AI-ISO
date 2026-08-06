"""The outgoing-delivery orchestrator (docs/057's own core feature).

Composes every other pure engine and service in this package: filters
and subscriptions decide *whether* an event fans out to an endpoint;
transformations reshape the payload; signatures authenticate it; the
retry engine decides *when* to try again; the endpoint's own health
tracks whether it should keep being tried at all.

**The endpoint URL is re-validated for SSRF safety at delivery time, not
only at registration time.** A hostname that resolved to a public IP
when the endpoint was registered can be re-pointed at a private one
later (DNS rebinding) -- see ``app/security/url_safety.py``'s own
docstring.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from app.events.webhook_events import (
    SOURCE_SERVICE,
    WebhookDeliveredEvent,
    WebhookFailedEvent,
    WebhookRetriedEvent,
)
from app.models.delivery import WebhookDelivery, WebhookDeliveryAttempt
from app.models.endpoint import WebhookEndpoint
from app.models.enums import DeliveryMode, DeliveryStatus, RetryBackoffStrategy
from app.models.event import WebhookEvent
from app.models.retry import WebhookDeadLetter, WebhookRetryQueueEntry
from app.repositories.delivery import WebhookDeliveryAttemptRepository, WebhookDeliveryRepository
from app.repositories.endpoint import WebhookEndpointRepository
from app.repositories.retry import WebhookDeadLetterRepository, WebhookRetryQueueRepository
from app.retry import engine as retry_engine
from app.security.url_safety import assert_safe_url
from app.services.filter import FilterService
from app.services.signature import SignatureService
from app.services.subscription import SubscriptionService
from app.services.transformation import TransformationService
from app.signatures import engine as signatures_engine
from app.subscriptions.engine import EventContext
from app.types import EventPublisher


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """The result of one delivery attempt."""

    delivery: WebhookDelivery
    attempt: WebhookDeliveryAttempt
    dead_lettered: bool


class DeliveryService:
    """Fans an event out to matching endpoints, then executes each delivery."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        deliveries: WebhookDeliveryRepository,
        attempts: WebhookDeliveryAttemptRepository,
        endpoints: WebhookEndpointRepository,
        retry_queue: WebhookRetryQueueRepository,
        dead_letters: WebhookDeadLetterRepository,
        subscriptions: SubscriptionService,
        filters: FilterService,
        transformations: TransformationService,
        signatures: SignatureService,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._http_client = http_client
        self._deliveries = deliveries
        self._attempts = attempts
        self._endpoints = endpoints
        self._retry_queue = retry_queue
        self._dead_letters = dead_letters
        self._subscriptions = subscriptions
        self._filters = filters
        self._transformations = transformations
        self._signatures = signatures
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def fan_out(
        self, organization_id: UUID, event: WebhookEvent, *, replay_job_id: UUID | None = None
    ) -> list[WebhookDelivery]:
        """Create one queued delivery per endpoint whose own subscription matches *event*."""
        context = EventContext(
            event_type=event.event_type,
            organization_id=str(organization_id),
            project_id=str(event.project_id) if event.project_id else None,
        )
        matching = await self._subscriptions.resolve_matching(organization_id, context)

        created: list[WebhookDelivery] = []
        for subscription in matching:
            event_attributes = {
                "organization_id": str(organization_id),
                "event_type": event.event_type,
                "severity": event.severity,
                "status": event.status,
                "tags": event.tags,
                "labels": event.labels,
                "metadata": event.payload,
            }
            if not await self._filters.passes(subscription.id, event_attributes):
                continue
            endpoint = await self._endpoints.require_in_org(organization_id, subscription.endpoint_id)
            if not endpoint.enabled:
                continue
            created.append(
                await self._deliveries.create(
                    WebhookDelivery(
                        organization_id=organization_id,
                        event_id=event.id,
                        endpoint_id=endpoint.id,
                        subscription_id=subscription.id,
                        mode=DeliveryMode.QUEUED,
                        status=DeliveryStatus.QUEUED,
                        payload=dict(event.payload),
                        headers=dict(event.headers),
                        idempotency_key=event.idempotency_key,
                        max_attempts=endpoint.max_attempts or 8,
                        replay_job_id=replay_job_id,
                    )
                )
            )
        return created

    async def deliver(self, organization_id: UUID, delivery: WebhookDelivery) -> DeliveryOutcome:
        """Execute one delivery attempt against its own endpoint.

        Raises:
            ValidationError: If the endpoint's own URL no longer
                resolves to a safe, public address.
        """
        endpoint = await self._endpoints.require_in_org(organization_id, delivery.endpoint_id)
        await assert_safe_url(endpoint.url)

        rules = await self._transformations.list_for_endpoint(endpoint.id)
        payload, headers = TransformationService.apply_all(
            rules, payload=delivery.payload, headers=dict(delivery.headers)
        )
        headers.update(endpoint.headers)
        body = json.dumps(payload).encode("utf-8")

        secret = await self._signatures.active_secret_for(endpoint.id)
        if secret is not None:
            headers.update(
                signatures_engine.build_signed_headers(
                    body,
                    secret=secret.secret,
                    algorithm=secret.algorithm,
                    timestamp=int(time.time()),
                    nonce=uuid.uuid4().hex,
                )
            )
        headers["Content-Type"] = "application/json"

        attempt_number = delivery.attempt_count + 1
        started = time.perf_counter()
        try:
            response = await self._http_client.post(
                endpoint.url, content=body, headers=headers, timeout=endpoint.timeout_seconds
            )
            latency_ms = (time.perf_counter() - started) * 1_000
            succeeded = response.status_code < 400
            attempt = await self._attempts.create(
                WebhookDeliveryAttempt(
                    organization_id=organization_id,
                    delivery_id=delivery.id,
                    attempt_number=attempt_number,
                    status_code=response.status_code,
                    response_headers=dict(response.headers),
                    response_body=response.text[:4_096],
                    latency_ms=latency_ms,
                    attempted_at=datetime.now(UTC),
                )
            )
            error = None if succeeded else f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - started) * 1_000
            succeeded = False
            error = str(exc)
            attempt = await self._attempts.create(
                WebhookDeliveryAttempt(
                    organization_id=organization_id,
                    delivery_id=delivery.id,
                    attempt_number=attempt_number,
                    latency_ms=latency_ms,
                    error=error,
                    attempted_at=datetime.now(UTC),
                )
            )

        delivery.attempt_count = attempt_number
        await self._mark_endpoint_outcome(endpoint, succeeded=succeeded)

        if succeeded:
            delivery.status = DeliveryStatus.DELIVERED
            delivery.delivered_at = datetime.now(UTC)
            await self._deliveries.update(delivery)
            await self._clear_retry(delivery.id)
            await self._publish_event(
                WebhookDeliveredEvent(
                    source_service=SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={"delivery_id": str(delivery.id), "endpoint_id": str(endpoint.id)},
                )
            )
            return DeliveryOutcome(delivery=delivery, attempt=attempt, dead_lettered=False)

        delivery.last_error = error
        await self._publish_event(
            WebhookFailedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"delivery_id": str(delivery.id), "endpoint_id": str(endpoint.id), "error": error},
            )
        )

        if not retry_engine.has_attempts_remaining(attempt_number, max_attempts=delivery.max_attempts):
            delivery.status = DeliveryStatus.EXPIRED
            await self._deliveries.update(delivery)
            await self._dead_letter(organization_id, delivery, endpoint, error=error)
            return DeliveryOutcome(delivery=delivery, attempt=attempt, dead_lettered=True)

        delivery.status = DeliveryStatus.RETRIED
        await self._deliveries.update(delivery)
        await self._schedule_retry(delivery, endpoint, attempt_number=attempt_number, error=error)
        await self._publish_event(
            WebhookRetriedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"delivery_id": str(delivery.id), "attempt_number": attempt_number},
            )
        )
        return DeliveryOutcome(delivery=delivery, attempt=attempt, dead_lettered=False)

    async def _mark_endpoint_outcome(self, endpoint: WebhookEndpoint, *, succeeded: bool) -> None:
        now = datetime.now(UTC)
        if succeeded:
            endpoint.consecutive_failures = 0
            endpoint.last_delivered_at = now
        else:
            endpoint.consecutive_failures += 1
            endpoint.last_failed_at = now
        await self._endpoints.update(endpoint)

    async def _clear_retry(self, delivery_id: UUID) -> None:
        existing = await self._retry_queue.get_for_delivery(delivery_id)
        if existing is not None:
            await self._retry_queue.delete(existing.id)

    async def _schedule_retry(
        self,
        delivery: WebhookDelivery,
        endpoint: WebhookEndpoint,
        *,
        attempt_number: int,
        error: str | None,
    ) -> None:
        strategy = RetryBackoffStrategy(endpoint.backoff_strategy or RetryBackoffStrategy.EXPONENTIAL)
        delay_seconds = retry_engine.compute_delay(
            attempt_number, strategy=strategy, base_seconds=5.0, max_seconds=3_600.0
        )
        existing = await self._retry_queue.get_for_delivery(delivery.id)
        next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

        entry = existing or WebhookRetryQueueEntry(
            organization_id=delivery.organization_id, delivery_id=delivery.id
        )
        entry.attempt_number = attempt_number
        entry.backoff_strategy = strategy
        entry.next_attempt_at = next_attempt_at
        entry.last_error = error
        if existing is None:
            await self._retry_queue.create(entry)
        else:
            await self._retry_queue.update(entry)

    async def _dead_letter(
        self,
        organization_id: UUID,
        delivery: WebhookDelivery,
        endpoint: WebhookEndpoint,
        *,
        error: str | None,
    ) -> None:
        await self._clear_retry(delivery.id)
        await self._dead_letters.create(
            WebhookDeadLetter(
                organization_id=organization_id,
                delivery_id=delivery.id,
                endpoint_id=endpoint.id,
                attempt_count=delivery.attempt_count,
                last_error=error,
                dead_lettered_at=datetime.now(UTC),
            )
        )


__all__ = ["DeliveryOutcome", "DeliveryService"]
