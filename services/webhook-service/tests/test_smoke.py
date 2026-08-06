"""Throwaway smoke test verifying the test foundation against real infra.

Superseded once the full suite lands; kept only long enough to prove
`conftest.py` actually works end to end before parallel agents build on it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from shared_core.exceptions.validation import ValidationError

from app.models.enums import DeliveryStatus, EventSource, SubscriptionScope
from app.services.delivery import DeliveryService
from app.services.endpoint import EndpointService
from app.services.event import EventService
from tests.conftest import FAKE_BACKEND_URL, HTTP_OK


async def test_endpoint_registration_round_trips(
    endpoint_service: EndpointService, organization_id: uuid.UUID
) -> None:
    created = await endpoint_service.register(
        organization_id, name="smoke-endpoint", url=f"{FAKE_BACKEND_URL}/echo"
    )
    fetched = await endpoint_service.get(organization_id, created.id)
    assert fetched.id == created.id
    assert fetched.name == "smoke-endpoint"


async def test_ssrf_protection_blocks_private_addresses(
    endpoint_service: EndpointService, organization_id: uuid.UUID
) -> None:
    with pytest.raises(ValidationError):
        await endpoint_service.register(
            organization_id, name="unsafe-endpoint", url="http://169.254.169.254/latest/meta-data"
        )


async def test_event_fan_out_and_delivery_round_trip(
    make_endpoint,
    make_subscription,
    event_service: EventService,
    delivery_service: DeliveryService,
    organization_id: uuid.UUID,
) -> None:
    endpoint = await make_endpoint()
    await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)

    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="order.created", payload={"id": "123"}
    )
    deliveries = await delivery_service.fan_out(organization_id, event)
    assert len(deliveries) == 1
    assert deliveries[0].status == DeliveryStatus.QUEUED

    outcome = await delivery_service.deliver(organization_id, deliveries[0])
    assert outcome.dead_lettered is False
    assert outcome.delivery.status == DeliveryStatus.DELIVERED
    assert outcome.attempt.status_code == HTTP_OK


async def test_signed_delivery_verifies_on_the_receiving_end(
    make_endpoint,
    make_signature,
    event_service: EventService,
    delivery_service: DeliveryService,
    organization_id: uuid.UUID,
) -> None:
    endpoint = await make_endpoint()
    await make_signature(endpoint.id, secret="shared-secret-value")

    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="order.signed", payload={"hello": "world"}
    )
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    outcome = await delivery_service.deliver(organization_id, delivery)
    assert outcome.delivery.status == DeliveryStatus.DELIVERED


async def test_dead_letter_after_exhausting_retries(
    make_endpoint,
    event_service: EventService,
    delivery_service: DeliveryService,
    organization_id: uuid.UUID,
) -> None:
    endpoint = await make_endpoint(url=f"{FAKE_BACKEND_URL}/error", max_attempts=1)
    event = await event_service.ingest_internal(
        organization_id, source=EventSource.CUSTOM, event_type="order.failed", payload={}
    )
    delivery = await delivery_service.queue_direct(organization_id, event, endpoint_id=endpoint.id)
    outcome = await delivery_service.deliver(organization_id, delivery)
    assert outcome.dead_lettered is True
    assert outcome.delivery.status == DeliveryStatus.EXPIRED


async def test_http_app_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == HTTP_OK
