"""This service's own domain events (docs/056 "EVENTS").

Every class below is a declarative `DomainEvent` subclass whose only real
behaviour is the `@default_registry.register` decorator applied at import
time. Light coverage is intentional: confirm each is actually registered
under its own `event_name` (the publisher refuses an unregistered event --
see `app/events/gateway_events.py`'s own docstring), and that constructing
one carries the fields every event needs.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

from app.events.gateway_events import (
    SOURCE_SERVICE,
    ApiAuthenticationFailedEvent,
    ApiAuthorizationDeniedEvent,
    ApiRequestCompletedEvent,
    ApiRequestReceivedEvent,
    CircuitBreakerOpenedEvent,
    GatewayHealthChangedEvent,
    QuotaExceededEvent,
    RateLimitExceededEvent,
)

EVENT_CLASSES = [
    (ApiRequestReceivedEvent, "ApiRequestReceived"),
    (ApiRequestCompletedEvent, "ApiRequestCompleted"),
    (ApiAuthenticationFailedEvent, "ApiAuthenticationFailed"),
    (ApiAuthorizationDeniedEvent, "ApiAuthorizationDenied"),
    (RateLimitExceededEvent, "RateLimitExceeded"),
    (QuotaExceededEvent, "QuotaExceeded"),
    (CircuitBreakerOpenedEvent, "CircuitBreakerOpened"),
    (GatewayHealthChangedEvent, "GatewayHealthChanged"),
]


@pytest.mark.parametrize("event_cls, expected_name", EVENT_CLASSES)
def test_event_name_matches_docs_vocabulary(
    event_cls: type[DomainEvent], expected_name: str
) -> None:
    assert event_cls.event_name == expected_name


@pytest.mark.parametrize("event_cls, expected_name", EVENT_CLASSES)
def test_event_is_registered_with_the_default_registry(
    event_cls: type[DomainEvent], expected_name: str
) -> None:
    assert default_registry.is_registered(expected_name)
    assert default_registry.lookup(expected_name) is event_cls


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_an_event_carries_its_source_service_org_and_payload(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    organization_id = uuid.uuid4()
    event = event_cls(
        source_service=SOURCE_SERVICE,
        organization_id=organization_id,
        payload={"request_id": "abc-123"},
    )
    assert event.source_service == SOURCE_SERVICE
    assert event.organization_id == organization_id
    assert event.payload == {"request_id": "abc-123"}
    assert isinstance(event, DomainEvent)


def test_every_event_is_a_distinct_class_under_its_own_name() -> None:
    # A copy-paste that forgot to change `event_name` would silently
    # shadow another event in the registry rather than fail loudly.
    names = [expected_name for _cls, expected_name in EVENT_CLASSES]
    assert len(names) == len(set(names))
