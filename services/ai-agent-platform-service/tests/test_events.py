"""This service's own domain events (docs/060 "EVENTS").

Every class in ``app/events/agent_events.py`` is a declarative
``DomainEvent`` subclass whose only real behaviour is the
``@default_registry.register`` decorator applied at import time. These
tests confirm each event is registered under its own ``event_name``,
carries the fields every :class:`~shared_core.events.base.BaseEvent`
defines (with the right defaults), and is a genuinely distinct class --
matching the light-coverage-but-thorough idiom every prior AI-IOS
service's own ``test_events.py`` (e.g. ``webhook-service``) already
established.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError
from shared_core.events import default_registry
from shared_core.events.base import BaseEvent, DomainEvent, EventType

from app.events.agent_events import (
    AgentCompletedEvent,
    AgentFailedEvent,
    AgentRegisteredEvent,
    AgentStartedEvent,
    ApprovalRequestedEvent,
    EvaluationCompletedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    ToolInvokedEvent,
)

SOURCE_SERVICE = "ai-agent-platform-service"

EVENT_CLASSES = [
    (AgentRegisteredEvent, "AgentRegistered"),
    (AgentStartedEvent, "AgentStarted"),
    (AgentCompletedEvent, "AgentCompleted"),
    (AgentFailedEvent, "AgentFailed"),
    (TaskCreatedEvent, "TaskCreated"),
    (TaskCompletedEvent, "TaskCompleted"),
    (ToolInvokedEvent, "ToolInvoked"),
    (ApprovalRequestedEvent, "ApprovalRequested"),
    (EvaluationCompletedEvent, "EvaluationCompleted"),
]


# ---- event_name / registration ---------------------------------------------


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


def test_every_event_is_a_distinct_class_under_its_own_name() -> None:
    # A copy-paste that forgot to change `event_name` would silently
    # shadow another event in the registry rather than fail loudly.
    names = [expected_name for _cls, expected_name in EVENT_CLASSES]
    assert len(names) == len(set(names))
    classes = [cls for cls, _name in EVENT_CLASSES]
    assert len(classes) == len(set(classes))


def test_every_event_name_is_present_in_all_event_names() -> None:
    all_names = default_registry.all_event_names()
    for _cls, expected_name in EVENT_CLASSES:
        assert expected_name in all_names


# ---- base shape / defaults --------------------------------------------------


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_every_event_is_a_domain_event(event_cls: type[DomainEvent], _expected_name: str) -> None:
    assert issubclass(event_cls, DomainEvent)
    assert issubclass(event_cls, BaseEvent)
    assert event_cls.event_type is EventType.DOMAIN
    assert event_cls.event_version == "v1"


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_constructing_requires_only_source_service(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    event = event_cls(source_service=SOURCE_SERVICE)
    assert event.source_service == SOURCE_SERVICE
    assert isinstance(event, DomainEvent)


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_missing_source_service_raises(event_cls: type[DomainEvent], _expected_name: str) -> None:
    with pytest.raises(ValidationError):
        event_cls()


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_default_field_values_outside_a_request_context(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    event = event_cls(source_service=SOURCE_SERVICE)

    # Auto-populated from the request context; unbound in a plain unit
    # test, so every one of these is honestly None/{} rather than a
    # fabricated placeholder.
    assert event.organization_id is None
    assert event.project_id is None
    assert event.user_id is None
    assert event.correlation_id is None
    assert event.request_id is None
    assert event.payload == {}
    assert event.metadata == {}

    assert isinstance(event.event_id, uuid.UUID)
    assert isinstance(event.timestamp, datetime)


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_two_instances_get_distinct_event_ids(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    first = event_cls(source_service=SOURCE_SERVICE)
    second = event_cls(source_service=SOURCE_SERVICE)
    assert first.event_id != second.event_id


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_an_event_carries_its_source_service_org_and_payload(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    organization_id = uuid.uuid4()
    project_id = uuid.uuid4()
    event = event_cls(
        source_service=SOURCE_SERVICE,
        organization_id=organization_id,
        project_id=project_id,
        payload={"agent_id": "abc-123"},
        metadata={"trace_id": "trace-xyz"},
    )
    assert event.source_service == SOURCE_SERVICE
    assert event.organization_id == organization_id
    assert event.project_id == project_id
    assert event.payload == {"agent_id": "abc-123"}
    assert event.metadata == {"trace_id": "trace-xyz"}


@pytest.mark.parametrize("event_cls, expected_name", EVENT_CLASSES)
def test_event_name_is_a_classvar_not_a_model_field(
    event_cls: type[DomainEvent], expected_name: str
) -> None:
    event = event_cls(source_service=SOURCE_SERVICE)
    # event_name is a ClassVar (docs/020 "EVENT NAMING"), so it is
    # excluded from the pydantic model's own field set / serialized dump.
    assert "event_name" not in type(event).model_fields
    assert event.event_name == expected_name


@pytest.mark.parametrize("event_cls, _expected_name", EVENT_CLASSES)
def test_serializes_to_json_with_expected_keys(
    event_cls: type[DomainEvent], _expected_name: str
) -> None:
    event = event_cls(source_service=SOURCE_SERVICE, payload={"foo": "bar"})
    dumped = event.model_dump(mode="json")

    assert dumped["source_service"] == SOURCE_SERVICE
    assert dumped["payload"] == {"foo": "bar"}
    assert isinstance(dumped["event_id"], str)
    assert isinstance(dumped["timestamp"], str)

    # Round-trips through JSON cleanly -- the shape any queue-backed
    # publisher relies on when serializing an event onto the wire.
    json_text = event.model_dump_json()
    assert isinstance(json_text, str)
    assert SOURCE_SERVICE in json_text
