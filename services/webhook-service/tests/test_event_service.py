"""EventService and WebhookEventRepository: internal ingestion, incoming-webhook
signature verification, and event-level idempotency dedup (docs/057 "WEBHOOK
TYPES", "EVENT SOURCES").

Against real PostgreSQL, in a SAVEPOINT-isolated session per test. Incoming
webhook signatures are built for real via ``app.signatures.engine
.build_signed_headers`` -- the same function ``DeliveryService`` uses to sign
an outgoing delivery -- so ``EventService.ingest_incoming`` verifies a
genuinely valid signature, never a stubbed one.
"""

from __future__ import annotations

import time
import uuid

import pytest
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import EventSource, SignatureAlgorithm, WebhookKind
from app.models.event import WebhookEvent
from app.services.event import EventService
from app.signatures import engine as signatures_engine
from tests.conftest import ago, soon, utcnow

pytestmark = pytest.mark.asyncio


def _sign(
    body: bytes, *, secret: str, algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256
):
    """Build a genuinely valid signed-request header set, plus the timestamp/nonce used."""
    timestamp = int(time.time())
    nonce = uuid.uuid4().hex
    headers = signatures_engine.build_signed_headers(
        body, secret=secret, algorithm=algorithm, timestamp=timestamp, nonce=nonce
    )
    return headers, timestamp, nonce


class TestIngestInternal:
    async def test_creates_an_internal_event_with_defaults(self, event_service, organization_id):
        created = await event_service.ingest_internal(
            organization_id,
            source=EventSource.AUTOMATION,
            event_type="automation.triggered",
            payload={"a": 1},
        )
        assert created.kind == WebhookKind.INTERNAL_EVENT
        assert created.source == EventSource.AUTOMATION
        assert created.event_type == "automation.triggered"
        assert created.payload == {"a": 1}
        assert created.severity is None
        assert created.status is None
        assert created.tags == []
        assert created.labels == {}
        assert created.idempotency_key is None
        assert created.correlation_id is None

    async def test_sets_provided_optional_fields(self, event_service, organization_id):
        created = await event_service.ingest_internal(
            organization_id,
            source=EventSource.MONITORING,
            event_type="monitor.alert",
            payload={"x": 1},
            severity="critical",
            status="open",
            tags=["a", "b"],
            labels={"k": "v"},
            correlation_id="corr-1",
        )
        assert created.severity == "critical"
        assert created.status == "open"
        assert created.tags == ["a", "b"]
        assert created.labels == {"k": "v"}
        assert created.correlation_id == "corr-1"

    async def test_publishes_webhook_received_event(
        self, event_service, organization_id, publisher
    ):
        created = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="custom.thing", payload={}
        )
        assert publisher.names == ["WebhookReceived"]
        assert publisher.events[0].payload["event_id"] == str(created.id)
        assert publisher.events[0].payload["event_type"] == "custom.thing"
        assert publisher.events[0].organization_id == organization_id

    async def test_does_not_publish_without_an_injected_publisher(
        self, events_repo, organization_id
    ):
        # `publish_event` is optional -- a service built without one (unlike
        # the `event_service` fixture, which always wires the recording
        # `publisher`) must still ingest successfully.
        bare_service = EventService(events_repo)
        created = await bare_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="silent.event", payload={}
        )
        assert created.event_type == "silent.event"

    async def test_a_second_call_with_the_same_idempotency_key_returns_the_first_row(
        self, event_service, organization_id, publisher
    ):
        first = await event_service.ingest_internal(
            organization_id,
            source=EventSource.CUSTOM,
            event_type="dup.event",
            payload={"n": 1},
            idempotency_key="dedupe-key-1",
        )
        second = await event_service.ingest_internal(
            organization_id,
            source=EventSource.CUSTOM,
            event_type="different.type",
            payload={"n": 2},
            idempotency_key="dedupe-key-1",
        )
        assert second.id == first.id
        # The second call's own arguments never took effect -- the first
        # row's own data is what's returned, verbatim.
        assert second.event_type == "dup.event"
        assert second.payload == {"n": 1}
        # No second `create`, so no second publish either.
        assert publisher.names == ["WebhookReceived"]

    async def test_a_different_idempotency_key_creates_a_second_row(
        self, event_service, organization_id
    ):
        first = await event_service.ingest_internal(
            organization_id,
            source=EventSource.CUSTOM,
            event_type="a",
            payload={},
            idempotency_key="key-a",
        )
        second = await event_service.ingest_internal(
            organization_id,
            source=EventSource.CUSTOM,
            event_type="a",
            payload={},
            idempotency_key="key-b",
        )
        assert first.id != second.id

    async def test_the_same_idempotency_key_in_a_different_org_is_not_a_duplicate(
        self, event_service, organization_id
    ):
        first = await event_service.ingest_internal(
            organization_id,
            source=EventSource.CUSTOM,
            event_type="a",
            payload={},
            idempotency_key="shared-key",
        )
        other_org = uuid.uuid4()
        second = await event_service.ingest_internal(
            other_org,
            source=EventSource.CUSTOM,
            event_type="a",
            payload={},
            idempotency_key="shared-key",
        )
        assert first.id != second.id

    async def test_no_idempotency_key_never_dedupes_across_calls(
        self, event_service, organization_id
    ):
        first = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="repeatable", payload={}
        )
        second = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="repeatable", payload={}
        )
        assert first.id != second.id


class TestIngestIncoming:
    async def test_a_validly_signed_request_is_recorded_and_both_events_publish_in_order(
        self,
        event_service,
        signature_service,
        make_endpoint,
        make_signature,
        organization_id,
        publisher,
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'
        headers, timestamp, nonce = _sign(body, secret="shared-secret-value")

        created = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={"ping": "pong"},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
        )

        assert created.kind == WebhookKind.INCOMING
        assert created.source == EventSource.CUSTOM
        assert created.event_type == "webhook.received"
        assert created.payload == {"ping": "pong"}
        assert created.headers == dict(headers)

        assert publisher.names == ["WebhookReceived", "WebhookValidated"]
        assert publisher.events[0].payload["event_id"] == str(created.id)
        assert publisher.events[1].payload["event_id"] == str(created.id)
        assert publisher.events[1].payload["secret_version"] == 1

    async def test_accepts_a_signature_from_a_rotating_older_secret(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="old-secret")
        await signature_service.rotate(
            organization_id, endpoint_id=endpoint.id, new_secret="new-secret", overlap_hours=24
        )
        body = b'{"ping":"pong"}'
        # Signed under the *old* (now ROTATING) secret -- still usable during
        # the overlap window, per SignatureService.rotate's own docstring.
        headers, timestamp, nonce = _sign(body, secret="old-secret")

        created = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={"ping": "pong"},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
        )
        assert created.id is not None

    async def test_raises_authentication_error_for_a_stale_timestamp(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'
        stale_timestamp = int(time.time()) - 3600
        nonce = uuid.uuid4().hex
        headers = signatures_engine.build_signed_headers(
            body,
            secret="shared-secret-value",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=stale_timestamp,
            nonce=nonce,
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await event_service.ingest_incoming(
                organization_id,
                endpoint_id=endpoint.id,
                event_type="webhook.received",
                body=body,
                payload={"ping": "pong"},
                headers=dict(headers),
                signature=headers["X-Webhook-Signature"],
                timestamp=stale_timestamp,
                nonce=nonce,
                signatures=signature_service,
                tolerance_seconds=300,
            )
        assert exc_info.value.status_code == 401

    async def test_raises_authentication_error_for_a_signature_that_matches_no_secret(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="the-real-secret")
        body = b'{"ping":"pong"}'
        # Signed under the wrong secret entirely.
        headers, timestamp, nonce = _sign(body, secret="an-attackers-guess")

        with pytest.raises(AuthenticationError):
            await event_service.ingest_incoming(
                organization_id,
                endpoint_id=endpoint.id,
                event_type="webhook.received",
                body=body,
                payload={"ping": "pong"},
                headers=dict(headers),
                signature=headers["X-Webhook-Signature"],
                timestamp=timestamp,
                nonce=nonce,
                signatures=signature_service,
                tolerance_seconds=300,
            )

    async def test_raises_authentication_error_when_the_endpoint_has_no_signing_secret_at_all(
        self, event_service, signature_service, make_endpoint, organization_id
    ):
        endpoint = await make_endpoint()  # no `make_signature` call at all
        body = b'{"ping":"pong"}'
        headers, timestamp, nonce = _sign(body, secret="whatever")

        with pytest.raises(AuthenticationError):
            await event_service.ingest_incoming(
                organization_id,
                endpoint_id=endpoint.id,
                event_type="webhook.received",
                body=body,
                payload={"ping": "pong"},
                headers=dict(headers),
                signature=headers["X-Webhook-Signature"],
                timestamp=timestamp,
                nonce=nonce,
                signatures=signature_service,
                tolerance_seconds=300,
            )

    async def test_a_second_call_with_the_same_idempotency_key_returns_the_first_row(
        self,
        event_service,
        signature_service,
        make_endpoint,
        make_signature,
        organization_id,
        publisher,
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'

        headers, timestamp, nonce = _sign(body, secret="shared-secret-value")
        first = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={"ping": "pong"},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
            idempotency_key="incoming-dedupe-key",
        )
        assert publisher.names == ["WebhookReceived", "WebhookValidated"]

        # A genuine retry: freshly signed (a real partner recomputes its own
        # signature per attempt), same idempotency key.
        headers2, timestamp2, nonce2 = _sign(body, secret="shared-secret-value")
        second = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={"ping": "pong"},
            headers=dict(headers2),
            signature=headers2["X-Webhook-Signature"],
            timestamp=timestamp2,
            nonce=nonce2,
            signatures=signature_service,
            tolerance_seconds=300,
            idempotency_key="incoming-dedupe-key",
        )
        assert second.id == first.id
        # No second create, so no second pair of publishes.
        assert publisher.names == ["WebhookReceived", "WebhookValidated"]

    async def test_dedup_does_not_bypass_signature_verification_on_the_retry_itself(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        # NOTE: signature verification runs unconditionally, *before* the
        # idempotency-key dedup lookup -- so a "duplicate" call whose own
        # signature does not itself verify (e.g. a stale timestamp) is still
        # rejected, even though the same key was already ingested once
        # successfully. See this suite's own module docstring / the final
        # report for more on this.
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'

        headers, timestamp, nonce = _sign(body, secret="shared-secret-value")
        await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={"ping": "pong"},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
            idempotency_key="retry-must-still-verify",
        )

        stale_timestamp = int(time.time()) - 3600
        stale_nonce = uuid.uuid4().hex
        stale_headers = signatures_engine.build_signed_headers(
            body,
            secret="shared-secret-value",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=stale_timestamp,
            nonce=stale_nonce,
        )
        with pytest.raises(AuthenticationError):
            await event_service.ingest_incoming(
                organization_id,
                endpoint_id=endpoint.id,
                event_type="webhook.received",
                body=body,
                payload={"ping": "pong"},
                headers=dict(stale_headers),
                signature=stale_headers["X-Webhook-Signature"],
                timestamp=stale_timestamp,
                nonce=stale_nonce,
                signatures=signature_service,
                tolerance_seconds=300,
                idempotency_key="retry-must-still-verify",
            )

    async def test_default_correlation_id_is_none_when_not_supplied(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b"{}"
        headers, timestamp, nonce = _sign(body, secret="shared-secret-value")
        created = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
        )
        assert created.correlation_id is None
        assert created.idempotency_key is None

    async def test_sets_correlation_id_when_supplied(
        self, event_service, signature_service, make_endpoint, make_signature, organization_id
    ):
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b"{}"
        headers, timestamp, nonce = _sign(body, secret="shared-secret-value")
        created = await event_service.ingest_incoming(
            organization_id,
            endpoint_id=endpoint.id,
            event_type="webhook.received",
            body=body,
            payload={},
            headers=dict(headers),
            signature=headers["X-Webhook-Signature"],
            timestamp=timestamp,
            nonce=nonce,
            signatures=signature_service,
            tolerance_seconds=300,
            correlation_id="corr-42",
        )
        assert created.correlation_id == "corr-42"


class TestGet:
    async def test_returns_the_event_within_its_own_org(self, event_service, organization_id):
        created = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="a", payload={}
        )
        fetched = await event_service.get(organization_id, created.id)
        assert fetched.id == created.id

    async def test_raises_not_found_for_a_missing_event(self, event_service, organization_id):
        with pytest.raises(NotFoundError):
            await event_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(self, event_service, organization_id):
        created = await event_service.ingest_internal(
            organization_id, source=EventSource.CUSTOM, event_type="a", payload={}
        )
        with pytest.raises(NotFoundError):
            await event_service.get(uuid.uuid4(), created.id)


class TestEventRepository:
    """Direct repository coverage for paths ``EventService`` never itself calls."""

    async def test_list_for_org_returns_events_in_this_org(self, events_repo, organization_id):
        first = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="listed.one",
            )
        )
        second = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="listed.two",
            )
        )
        other_org_event = await events_repo.create(
            WebhookEvent(
                organization_id=uuid.uuid4(),
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="listed.other-org",
            )
        )
        found = await events_repo.list_for_org(organization_id)
        found_ids = {row.id for row in found}
        assert first.id in found_ids
        assert second.id in found_ids
        assert other_org_event.id not in found_ids

    async def test_list_for_org_filters_by_since(self, events_repo, organization_id):
        old = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="old.event",
                created_at=ago(7200),
            )
        )
        recent = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="recent.event",
                created_at=utcnow(),
            )
        )
        found = await events_repo.list_for_org(organization_id, since=ago(3600))
        found_ids = {row.id for row in found}
        assert recent.id in found_ids
        assert old.id not in found_ids

    async def test_list_for_org_filters_by_until(self, events_repo, organization_id):
        old = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="old.event.2",
                created_at=ago(7200),
            )
        )
        future = await events_repo.create(
            WebhookEvent(
                organization_id=organization_id,
                kind=WebhookKind.INTERNAL_EVENT,
                source=EventSource.CUSTOM,
                event_type="future.event",
                created_at=soon(7200),
            )
        )
        found = await events_repo.list_for_org(organization_id, until=utcnow())
        found_ids = {row.id for row in found}
        assert old.id in found_ids
        assert future.id not in found_ids

    async def test_list_for_org_respects_limit_and_offset(self, events_repo, organization_id):
        for i in range(3):
            await events_repo.create(
                WebhookEvent(
                    organization_id=organization_id,
                    kind=WebhookKind.INTERNAL_EVENT,
                    source=EventSource.CUSTOM,
                    event_type=f"paged.{i}",
                    created_at=ago(i),
                )
            )
        page = await events_repo.list_for_org(organization_id, limit=1, offset=1)
        assert len(page) == 1

    async def test_get_by_idempotency_key_returns_none_when_absent(
        self, events_repo, organization_id
    ):
        assert await events_repo.get_by_idempotency_key(organization_id, "nope") is None
