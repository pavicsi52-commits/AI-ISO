"""Enterprise Event Framework.

Event-driven communication backbone for AI-IOS
(docs/020_Enterprise_Event_Framework.md.txt "OBJECTIVE"): Event
Publishing, Event Consumption, Event Routing, Event Store, Event Replay,
Dead Letter Handling, Event Versioning, Event Validation, Event
Monitoring. Built on top of :mod:`shared_core.queue` (Prompt 012), which
remains the only module that talks to RabbitMQ directly -- this package
never reimplements broker transport, only what sits above it: typed
event envelopes, a registry, routing/dispatch, retry-with-backoff,
replay, and audit/metrics.
"""

from shared_core.events.audit import audit_consume, audit_failure, audit_publish, audit_replay
from shared_core.events.base import (
    BaseEvent,
    DomainEvent,
    EventType,
    IntegrationEvent,
    InternalEvent,
)
from shared_core.events.bus import EventBus
from shared_core.events.dead_letter import (
    DeadLetteredEvent,
    dead_letter_queue_name_for,
    inspect_dead_letters,
    purge_dead_letters,
    replay_dead_letters,
)
from shared_core.events.decorators import (
    event_handler,
    get_event_name,
    publishes,
    register_handlers,
)
from shared_core.events.dispatcher import (
    EventDispatcher,
    EventFilter,
    EventHandler,
    HandlerRegistration,
)
from shared_core.events.exceptions import (
    DeadLetterError,
    EventConsumeFailedError,
    EventPublishFailedError,
    EventRegistrationError,
    EventReplayError,
    EventValidationError,
    EventVersionMismatchError,
    SubscriberError,
)
from shared_core.events.factory import EventFramework, create_event_framework
from shared_core.events.health import EventHealthReport, check_event_framework_health
from shared_core.events.helpers import event_name_from_class, generate_correlation_id
from shared_core.events.manager import EventManager
from shared_core.events.metadata import build_metadata
from shared_core.events.middleware import ConsumeMiddleware, MiddlewareChain, PublishMiddleware
from shared_core.events.publisher import EventPublisher
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.replay import EventStore, ReplayCriteria, replay_events
from shared_core.events.retry import RetryPolicy, compute_backoff_delay, is_retryable
from shared_core.events.router import EventRouter, Route, RouteCondition
from shared_core.events.serializer import (
    compact_payload,
    deserialize_event,
    expand_payload,
    serialize_event,
)
from shared_core.events.subscriber import EventSubscriber
from shared_core.events.validator import mask_sensitive_payload, validate_event
from shared_core.events.versioning import VersionMigrator, is_compatible, parse_version

__all__ = [
    "BaseEvent",
    "ConsumeMiddleware",
    "DeadLetterError",
    "DeadLetteredEvent",
    "DomainEvent",
    "EventBus",
    "EventConsumeFailedError",
    "EventDispatcher",
    "EventFilter",
    "EventFramework",
    "EventHandler",
    "EventHealthReport",
    "EventManager",
    "EventPublishFailedError",
    "EventPublisher",
    "EventRegistrationError",
    "EventRegistry",
    "EventReplayError",
    "EventRouter",
    "EventStore",
    "EventSubscriber",
    "EventType",
    "EventValidationError",
    "EventVersionMismatchError",
    "HandlerRegistration",
    "IntegrationEvent",
    "InternalEvent",
    "MiddlewareChain",
    "PublishMiddleware",
    "ReplayCriteria",
    "RetryPolicy",
    "Route",
    "RouteCondition",
    "SubscriberError",
    "VersionMigrator",
    "audit_consume",
    "audit_failure",
    "audit_publish",
    "audit_replay",
    "build_metadata",
    "check_event_framework_health",
    "compact_payload",
    "compute_backoff_delay",
    "create_event_framework",
    "dead_letter_queue_name_for",
    "default_registry",
    "deserialize_event",
    "event_handler",
    "event_name_from_class",
    "expand_payload",
    "generate_correlation_id",
    "get_event_name",
    "inspect_dead_letters",
    "is_compatible",
    "is_retryable",
    "mask_sensitive_payload",
    "parse_version",
    "publishes",
    "purge_dead_letters",
    "register_handlers",
    "replay_dead_letters",
    "replay_events",
    "serialize_event",
    "validate_event",
]
