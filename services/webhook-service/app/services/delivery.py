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
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.repositories.filter import WebhookFilterRepository
from app.repositories.retry import WebhookDeadLetterRepository, WebhookRetryQueueRepository
from app.repositories.signature import WebhookSignatureRepository
from app.repositories.subscription import WebhookSubscriptionRepository
from app.repositories.transformation import WebhookTransformationRepository
from app.retry import engine as retry_engine
from app.security.url_safety import assert_safe_url
from app.services.filter import FilterService
from app.services.signature import SignatureService
from app.services.subscription import SubscriptionService
from app.services.transformation import TransformationService
from app.signatures import engine as signatures_engine
from app.subscriptions.engine import EventContext
from app.types import EventPublisher

_SUCCESS_STATUS_CEILING = 400
"""Below this HTTP status, a delivery attempt counts as successful."""


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

    async def get(self, organization_id: UUID, delivery_id: UUID) -> WebhookDelivery:
        """One delivery.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._deliveries.require_in_org(organization_id, delivery_id)

    async def list_deliveries(
        self,
        organization_id: UUID,
        *,
        status: DeliveryStatus | None = None,
        endpoint_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WebhookDelivery]:
        """Deliveries in this organization, newest first."""
        return await self._deliveries.list_for_org(
            organization_id, status=status, endpoint_id=endpoint_id, limit=limit, offset=offset
        )

    async def get_dead_letter(
        self, organization_id: UUID, dead_letter_id: UUID
    ) -> WebhookDeadLetter:
        """One dead-lettered delivery.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._dead_letters.require_in_org(organization_id, dead_letter_id)

    async def list_dead_letters(
        self, organization_id: UUID, *, replayed: bool | None = None, limit: int = 200
    ) -> list[WebhookDeadLetter]:
        """Dead-lettered deliveries in this organization, newest first."""
        return await self._dead_letters.list_for_org(
            organization_id, replayed=replayed, limit=limit
        )

    async def _schedule_first_attempt(self, delivery: WebhookDelivery) -> None:
        """Make a freshly-queued delivery due on the very next retry-sweep tick.

        `fan_out`/`queue_direct` only ever create a `QUEUED` delivery row
        -- without a corresponding `webhook_retry_queue` entry, nothing
        would ever call `deliver()` for it: `RetrySweepWorker` only walks
        rows already in that table, which otherwise only get created by
        `_schedule_retry` after a *failed* attempt. `next_attempt_at=now`
        makes the delivery due immediately, no backoff delay, since this
        is attempt one, not a retry of a prior failure.
        """
        await self._retry_queue.create(
            WebhookRetryQueueEntry(
                organization_id=delivery.organization_id,
                delivery_id=delivery.id,
                attempt_number=0,
                next_attempt_at=datetime.now(UTC),
            )
        )

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
            endpoint = await self._endpoints.require_in_org(
                organization_id, subscription.endpoint_id
            )
            if not endpoint.enabled:
                continue
            queued = await self._deliveries.create(
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
            await self._schedule_first_attempt(queued)
            created.append(queued)
        return created

    async def queue_direct(
        self,
        organization_id: UUID,
        event: WebhookEvent,
        *,
        endpoint_id: UUID,
    ) -> WebhookDelivery:
        """Queue one delivery straight to *endpoint_id*, bypassing subscription/filter resolution.

        For a caller that already knows exactly which endpoint should
        receive this event (docs/057's own ``POST /webhooks/outgoing``) --
        deliberately not subject to a subscription's own filters, since
        there is no subscription in this path to own them.
        """
        endpoint = await self._endpoints.require_in_org(organization_id, endpoint_id)
        queued = await self._deliveries.create(
            WebhookDelivery(
                organization_id=organization_id,
                event_id=event.id,
                endpoint_id=endpoint.id,
                subscription_id=None,
                mode=DeliveryMode.IMMEDIATE,
                status=DeliveryStatus.QUEUED,
                payload=dict(event.payload),
                headers=dict(event.headers),
                idempotency_key=event.idempotency_key,
                max_attempts=endpoint.max_attempts or 8,
            )
        )
        await self._schedule_first_attempt(queued)
        return queued

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
            succeeded = response.status_code < _SUCCESS_STATUS_CEILING
            attempt = await self._attempts.create(
                WebhookDeliveryAttempt(
                    organization_id=organization_id,
                    delivery_id=delivery.id,
                    endpoint_id=endpoint.id,
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
                    endpoint_id=endpoint.id,
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
                payload={
                    "delivery_id": str(delivery.id),
                    "endpoint_id": str(endpoint.id),
                    "error": error,
                },
            )
        )

        if not retry_engine.has_attempts_remaining(
            attempt_number, max_attempts=delivery.max_attempts
        ):
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
        strategy = RetryBackoffStrategy(
            endpoint.backoff_strategy or RetryBackoffStrategy.EXPONENTIAL
        )
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


def build_delivery_service(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    *,
    encryption_key: str,
    publish_event: EventPublisher | None = None,
) -> DeliveryService:
    """Build a fully-wired :class:`DeliveryService` from one session.

    The one-stop constructor a worker (its own session per tick, not a
    request) or any other caller outside the FastAPI dependency graph
    needs -- ``app/api/deps.py``'s own ``get_delivery_service`` wires
    the same pieces together for a request instead.
    """
    return DeliveryService(
        http_client=http_client,
        deliveries=WebhookDeliveryRepository(session),
        attempts=WebhookDeliveryAttemptRepository(session),
        endpoints=WebhookEndpointRepository(session),
        retry_queue=WebhookRetryQueueRepository(session),
        dead_letters=WebhookDeadLetterRepository(session),
        subscriptions=SubscriptionService(WebhookSubscriptionRepository(session)),
        filters=FilterService(WebhookFilterRepository(session)),
        transformations=TransformationService(WebhookTransformationRepository(session)),
        signatures=SignatureService(
            WebhookSignatureRepository(session), encryption_key=encryption_key
        ),
        publish_event=publish_event,
    )


__all__ = ["DeliveryOutcome", "DeliveryService", "build_delivery_service"]
