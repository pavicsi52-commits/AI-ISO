"""Base event model.

Fields per docs/020_Enterprise_Event_Framework.md.txt "EVENT FORMAT". This
is the Prompt 012 baseline, expanded with the previously-missing
``event_type`` field, auto-populated tenant/correlation fields, and the
three primary event-type base classes docs/020 gives their own deep-dive
sections to.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from shared_core.events.metadata import (
    default_correlation_id,
    default_organization_id,
    default_project_id,
    default_request_id,
    default_user_id,
)


class EventType(StrEnum):
    """Which of docs/020's "EVENT TYPES" an event belongs to."""

    DOMAIN = "domain"
    INTEGRATION = "integration"
    INTERNAL = "internal"
    SCHEDULED = "scheduled"
    SYSTEM = "system"
    AUDIT = "audit"
    NOTIFICATION = "notification"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    INVENTORY = "inventory"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    SECURITY = "security"
    AI = "ai"
    PLUGIN = "plugin"


class BaseEvent(BaseModel):
    """Base class every domain/integration/internal event inherits.

    Subclasses set :attr:`event_name` (past tense, e.g. ``"UserCreated"``
    -- docs/020 "EVENT NAMING") and typically :attr:`event_type`, and
    define their own ``payload`` shape by adding typed fields.
    Organization/project/user/correlation/request IDs auto-populate from
    the currently-bound request context when not given explicitly.
    """

    event_name: ClassVar[str] = "base.event"
    event_version: ClassVar[str] = "v1"
    event_type: ClassVar[EventType] = EventType.DOMAIN

    event_id: UUID = Field(default_factory=uuid4)
    source_service: str
    organization_id: UUID | None = Field(default_factory=default_organization_id)
    project_id: UUID | None = Field(default_factory=default_project_id)
    user_id: UUID | None = Field(default_factory=default_user_id)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = Field(default_factory=default_correlation_id)
    request_id: str | None = Field(default_factory=default_request_id)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainEvent(BaseEvent):
    """Represents a business fact (docs/020 "DOMAIN EVENTS"): ``UserCreated``, ``AssetDiscovered``.

    Published and consumed within the platform via the queue-backed
    publisher/subscriber, same as any other non-internal event.
    """

    event_type: ClassVar[EventType] = EventType.DOMAIN


class IntegrationEvent(BaseEvent):
    """Used between microservices (docs/020 "INTEGRATION EVENTS").

    Payloads must be stable and versioned, and must never expose internal
    database objects -- a service publishing one is responsible for
    shaping ``payload`` into a deliberate public contract, never
    serializing an ORM entity directly into it.
    """

    event_type: ClassVar[EventType] = EventType.INTEGRATION


class InternalEvent(BaseEvent):
    """Internal service communication only (docs/020 "INTERNAL EVENTS").

    "Never leave the owning service."

    Structurally enforced, not just documented:
    :class:`shared_core.events.bus.EventBus` dispatches ``InternalEvent``
    subclasses through its in-process handler registry only -- it never
    routes them through the queue-backed publisher, so there is no code
    path by which one could leave the process.
    """

    event_type: ClassVar[EventType] = EventType.INTERNAL


__all__ = ["BaseEvent", "DomainEvent", "EventType", "IntegrationEvent", "InternalEvent"]
