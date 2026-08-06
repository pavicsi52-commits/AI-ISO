"""HTTP-level tests for ``app/api/events.py``: ``POST /webhooks/events``
(internal), ``POST /webhooks/incoming`` (signed external), and
``POST /webhooks/outgoing`` (direct queue) -- docs/057 "WEBHOOK TYPES",
"REST APIs".

Real FastAPI app through ``httpx.ASGITransport`` (the ``client`` fixture),
real PostgreSQL underneath. An incoming signed request is built by hand with
``app.signatures.engine.build_signed_headers`` -- the exact function
``DeliveryService`` itself uses to sign an outgoing delivery -- so these
tests exercise genuine HMAC verification, never a stubbed signature.

Error bodies for ``AIIOSException`` subclasses go through
``shared_core.exceptions.register_exception_handlers``, which returns
``{"error": {"code": ..., ...}}``. ``AuthenticationError.error_code`` is the
one stable signal checked for a rejected incoming webhook -- never the raw
message text.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.api import deps
from app.models.enums import SignatureAlgorithm
from app.signatures import engine as signatures_engine
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio

AUTHENTICATION_ERROR_CODE = "AIIOS-AUTH-0001"
NOT_FOUND_ERROR_CODE = "AIIOS-NF-0001"
VALIDATION_ERROR_CODE = "AIIOS-VAL-0001"


def _sign(body: bytes, *, secret: str, algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256):
    timestamp = int(time.time())
    nonce = uuid.uuid4().hex
    headers = signatures_engine.build_signed_headers(
        body, secret=secret, algorithm=algorithm, timestamp=timestamp, nonce=nonce
    )
    return headers, timestamp, nonce


class TestRaiseInternalEvent:
    async def test_creates_event_returns_201_with_expected_shape(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/webhooks/events?organization_id={organization_id}",
            json={
                "source": "custom",
                "event_type": "order.created",
                "payload": {"id": "abc-123"},
            },
        )
        assert response.status_code == HTTP_CREATED
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["kind"] == "internal_event"
        assert data["source"] == "custom"
        assert data["event_type"] == "order.created"
        assert data["payload"] == {"id": "abc-123"}
        assert data["organization_id"] == str(organization_id)
        assert uuid.UUID(data["id"])

    async def test_missing_organization_id_query_param_is_a_validation_error(
        self, client: AsyncClient
    ) -> None:
        # Every FastAPI `RequestValidationError` (missing/invalid query param
        # or body field alike) is mapped by `shared_core`'s own global
        # handler to `ValidationError` -- HTTP 400, not FastAPI's default 422.
        response = await client.post(
            "/webhooks/events", json={"source": "custom", "event_type": "order.created"}
        )
        assert response.status_code == HTTP_BAD_REQUEST
        assert response.json()["error"]["code"] == VALIDATION_ERROR_CODE

    async def test_invalid_body_is_a_validation_error(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        # `event_type` has `min_length=1` -- an empty string fails schema validation.
        response = await client.post(
            f"/webhooks/events?organization_id={organization_id}",
            json={"source": "custom", "event_type": ""},
        )
        assert response.status_code == HTTP_BAD_REQUEST
        assert response.json()["error"]["code"] == VALIDATION_ERROR_CODE

    async def test_fans_out_to_a_matching_subscription(
        self, client: AsyncClient, make_endpoint, make_subscription, deliveries_repo, organization_id
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id)  # WILDCARD by default -- matches anything.

        response = await client.post(
            f"/webhooks/events?organization_id={organization_id}",
            json={"source": "custom", "event_type": "order.fanned-out", "payload": {}},
        )
        assert response.status_code == HTTP_CREATED
        event_id = uuid.UUID(response.json()["data"]["id"])

        deliveries = await deliveries_repo.list_for_org(organization_id, endpoint_id=endpoint.id)
        assert any(delivery.event_id == event_id for delivery in deliveries)

    async def test_idempotency_key_dedups_the_underlying_event_row(
        self, client: AsyncClient, events_repo, organization_id: uuid.UUID
    ) -> None:
        payload = {
            "source": "custom",
            "event_type": "order.created",
            "payload": {"id": "first"},
            "idempotency_key": "http-dedupe-key",
        }
        first = await client.post(f"/webhooks/events?organization_id={organization_id}", json=payload)
        second_payload = dict(payload, payload={"id": "second"})
        second = await client.post(
            f"/webhooks/events?organization_id={organization_id}", json=second_payload
        )

        assert first.status_code == HTTP_CREATED
        assert second.status_code == HTTP_CREATED
        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        assert second.json()["data"]["payload"] == {"id": "first"}  # the first call's own data won

        existing = await events_repo.get_by_idempotency_key(organization_id, "http-dedupe-key")
        assert existing is not None
        assert existing.payload == {"id": "first"}


class TestReceiveIncomingWebhook:
    @pytest.fixture(autouse=True)
    def _wire_the_apps_own_signature_dependency_to_this_suites_signature_service(
        self, app, signature_service
    ):
        # The real `app` fixture builds its own `SignatureSvc` from
        # `get_settings()`'s own process-wide, env-derived
        # `secret_encryption_key` -- a *different* key from the one the
        # `service_settings` test fixture randomly generates per test, which
        # is what `signature_service`/`make_signature` themselves use to
        # encrypt a secret. Left unwired, the route's own decrypt call fails
        # with "AESGCM key must be 128, 192, or 256 bits." (a garbled
        # ciphertext under the wrong key), for every single request here.
        # Overridden exactly like the `app` fixture's own
        # `get_db_session`/`get_http_client` overrides -- same encryption
        # key on both the write side (`make_signature`) and the read side
        # (this route's own signature verification).
        app.dependency_overrides[deps.get_signature_service] = lambda: signature_service
        yield
        app.dependency_overrides.pop(deps.get_signature_service, None)

    async def test_a_validly_signed_request_returns_201_with_expected_shape(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'
        headers, _timestamp, _nonce = _sign(body, secret="shared-secret-value")

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        data = response.json()["data"]
        assert data["kind"] == "incoming"
        assert data["event_type"] == "webhook.received"  # the route's own default
        assert data["payload"] == {"ping": "pong"}

    async def test_missing_signature_headers_entirely_is_401(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=b'{"ping":"pong"}',
        )
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_a_stale_timestamp_is_401(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
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

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_a_signature_computed_under_the_wrong_secret_is_401(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="the-real-secret")
        body = b'{"ping":"pong"}'
        headers, _timestamp, _nonce = _sign(body, secret="an-attackers-guess")

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["error"]["code"] == AUTHENTICATION_ERROR_CODE

    async def test_idempotency_key_header_dedups_at_the_http_layer(
        self, client: AsyncClient, make_endpoint, make_signature, events_repo, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b'{"ping":"pong"}'

        headers1, _t1, _n1 = _sign(body, secret="shared-secret-value")
        headers1["Idempotency-Key"] = "http-incoming-dedupe"
        first = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers1,
        )

        headers2, _t2, _n2 = _sign(body, secret="shared-secret-value")
        headers2["Idempotency-Key"] = "http-incoming-dedupe"
        second = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers2,
        )

        assert first.status_code == HTTP_CREATED
        assert second.status_code == HTTP_CREATED
        assert first.json()["data"]["id"] == second.json()["data"]["id"]

        existing = await events_repo.get_by_idempotency_key(organization_id, "http-incoming-dedupe")
        assert existing is not None
        assert existing.id == uuid.UUID(first.json()["data"]["id"])

    async def test_explicit_event_type_query_param_overrides_the_default(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b"{}"
        headers, _timestamp, _nonce = _sign(body, secret="shared-secret-value")

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}"
            "&event_type=partner.custom-event",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["event_type"] == "partner.custom-event"

    async def test_an_empty_body_becomes_an_empty_payload(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b""
        headers, _timestamp, _nonce = _sign(body, secret="shared-secret-value")

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["payload"] == {}

    async def test_correlation_id_header_is_passed_through(
        self, client: AsyncClient, make_endpoint, make_signature, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        await make_signature(endpoint.id, secret="shared-secret-value")
        body = b"{}"
        headers, _timestamp, _nonce = _sign(body, secret="shared-secret-value")
        headers["X-Correlation-Id"] = "corr-99"

        response = await client.post(
            f"/webhooks/incoming?organization_id={organization_id}&endpoint_id={endpoint.id}",
            content=body,
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["correlation_id"] == "corr-99"


class TestQueueOutgoingDelivery:
    async def test_queues_a_delivery_for_the_named_endpoint(
        self, client: AsyncClient, make_endpoint, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()

        response = await client.post(
            f"/webhooks/outgoing?organization_id={organization_id}",
            json={
                "endpoint_id": str(endpoint.id),
                "event_type": "direct.send",
                "payload": {"hello": "world"},
            },
        )
        assert response.status_code == HTTP_CREATED
        data = response.json()["data"]
        assert data["endpoint_id"] == str(endpoint.id)
        assert data["status"] == "queued"
        assert data["mode"] == "immediate"
        assert data["subscription_id"] is None
        assert data["attempt_count"] == 0
        assert uuid.UUID(data["event_id"])

    async def test_bypasses_subscription_resolution_even_with_no_subscription_registered(
        self, client: AsyncClient, make_endpoint, organization_id: uuid.UUID
    ) -> None:
        # No `make_subscription` call at all -- `/webhooks/outgoing` must
        # still queue a delivery straight to the named endpoint.
        endpoint = await make_endpoint()
        response = await client.post(
            f"/webhooks/outgoing?organization_id={organization_id}",
            json={"endpoint_id": str(endpoint.id), "event_type": "direct.send", "payload": {}},
        )
        assert response.status_code == HTTP_CREATED

    async def test_missing_body_fields_is_a_validation_error(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/webhooks/outgoing?organization_id={organization_id}", json={"event_type": "direct.send"}
        )
        assert response.status_code == HTTP_BAD_REQUEST
        assert response.json()["error"]["code"] == VALIDATION_ERROR_CODE

    async def test_an_unknown_endpoint_id_is_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/webhooks/outgoing?organization_id={organization_id}",
            json={"endpoint_id": str(uuid.uuid4()), "event_type": "direct.send", "payload": {}},
        )
        assert response.status_code == HTTP_NOT_FOUND
        assert response.json()["error"]["code"] == NOT_FOUND_ERROR_CODE

    async def test_idempotency_key_reuses_the_same_underlying_event(
        self, client: AsyncClient, make_endpoint, organization_id: uuid.UUID
    ) -> None:
        endpoint = await make_endpoint()
        payload = {
            "endpoint_id": str(endpoint.id),
            "event_type": "direct.send",
            "payload": {},
            "idempotency_key": "http-outgoing-dedupe",
        }
        first = await client.post(f"/webhooks/outgoing?organization_id={organization_id}", json=payload)
        second = await client.post(f"/webhooks/outgoing?organization_id={organization_id}", json=payload)

        assert first.status_code == HTTP_CREATED
        assert second.status_code == HTTP_CREATED
        # Both deliveries were queued for the same underlying (deduped) event.
        assert first.json()["data"]["event_id"] == second.json()["data"]["event_id"]
        # But each call queues its own delivery row -- `queue_direct` has no
        # dedup of its own, only `ingest_internal`'s own event-level dedup.
        assert first.json()["data"]["id"] != second.json()["data"]["id"]
