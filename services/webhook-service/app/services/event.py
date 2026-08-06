"""Webhook event ingestion (docs/057 "WEBHOOK TYPES", "EVENT SOURCES")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.authentication import AuthenticationError

from app.events.webhook_events import SOURCE_SERVICE, WebhookReceivedEvent, WebhookValidatedEvent
from app.models.enums import EventSource, WebhookKind
from app.models.event import WebhookEvent
from app.repositories.event import WebhookEventRepository
from app.services.signature import SignatureService
from app.signatures import engine as signatures_engine
from app.types import EventPublisher


class EventService:
    """Events received from an external caller or raised internally, before fan-out."""

    def __init__(
        self, events: WebhookEventRepository, *, publish_event: EventPublisher | None = None
    ) -> None:
        self._events = events
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def ingest_internal(
        self,
        organization_id: UUID,
        *,
        source: EventSource,
        event_type: str,
        payload: dict[str, Any],
        severity: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        labels: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> WebhookEvent:
        """Record an internally-raised event (automation, workflow runtime, etc.).

        Deduplicates by *idempotency_key* within this organization: a
        second call with the same key returns the row already recorded
        for the first, rather than creating a duplicate.
        """
        if idempotency_key is not None:
            existing = await self._events.get_by_idempotency_key(organization_id, idempotency_key)
            if existing is not None:
                return existing
        created = await self._events.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=source,
                event_type=event_type,
                payload=dict(payload),
                severity=severity,
                status=status,
                tags=list(tags or []),
                labels=dict(labels or {}),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        )
        await self._publish_event(
            WebhookReceivedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"event_id": str(created.id), "event_type": event_type},
            )
        )
        return created

    async def ingest_incoming(
        self,
        organization_id: UUID,
        *,
        endpoint_id: UUID,
        event_type: str,
        body: bytes,
        payload: dict[str, Any],
        headers: dict[str, str],
        signature: str,
        timestamp: int,
        nonce: str,
        signatures: SignatureService,
        tolerance_seconds: int,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> WebhookEvent:
        """Record an incoming webhook after verifying its own HMAC signature.

        Raises:
            AuthenticationError: If the timestamp has aged out, or no
                usable secret's signature matches the request.
        """
        candidates = await signatures.usable_secrets_for(endpoint_id)
        matched = signatures_engine.verify_signed_request(
            body,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            secrets=candidates,
            tolerance_seconds=tolerance_seconds,
        )
        if matched is None:
            raise AuthenticationError("Invalid or stale webhook signature.")

        if idempotency_key is not None:
            existing = await self._events.get_by_idempotency_key(organization_id, idempotency_key)
            if existing is not None:
                return existing
        created = await self._events.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INCOMING,
                source=EventSource.CUSTOM,
                event_type=event_type,
                payload=dict(payload),
                headers=dict(headers),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        )
        await self._publish_event(
            WebhookReceivedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"event_id": str(created.id), "event_type": event_type},
            )
        )
        await self._publish_event(
            WebhookValidatedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"event_id": str(created.id), "secret_version": matched.version},
            )
        )
        return created

    async def get(self, organization_id: UUID, event_id: UUID) -> WebhookEvent:
        """One event.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._events.require_in_org(organization_id, event_id)


__all__ = ["EventService"]
