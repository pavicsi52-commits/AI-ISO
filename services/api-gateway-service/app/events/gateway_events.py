"""Domain events this service publishes (docs/056 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every proxy call raises and the caller gets a 400 for a request that did
nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "api-gateway-service"


@default_registry.register
class ApiRequestReceivedEvent(DomainEvent):
    """A request arrived at the gateway."""

    event_name: ClassVar[str] = "ApiRequestReceived"


@default_registry.register
class ApiRequestCompletedEvent(DomainEvent):
    """A request finished being proxied, successfully or not."""

    event_name: ClassVar[str] = "ApiRequestCompleted"


@default_registry.register
class ApiAuthenticationFailedEvent(DomainEvent):
    """A caller failed to prove their identity."""

    event_name: ClassVar[str] = "ApiAuthenticationFailed"


@default_registry.register
class ApiAuthorizationDeniedEvent(DomainEvent):
    """An authenticated caller was denied by RBAC/ABAC."""

    event_name: ClassVar[str] = "ApiAuthorizationDenied"


@default_registry.register
class RateLimitExceededEvent(DomainEvent):
    """A caller exceeded a configured rate limit."""

    event_name: ClassVar[str] = "RateLimitExceeded"


@default_registry.register
class QuotaExceededEvent(DomainEvent):
    """A caller exceeded a configured quota."""

    event_name: ClassVar[str] = "QuotaExceeded"


@default_registry.register
class CircuitBreakerOpenedEvent(DomainEvent):
    """A backend instance's own circuit breaker tripped open."""

    event_name: ClassVar[str] = "CircuitBreakerOpened"


@default_registry.register
class GatewayHealthChangedEvent(DomainEvent):
    """A backend instance's own probed health changed state."""

    event_name: ClassVar[str] = "GatewayHealthChanged"


__all__ = [
    "SOURCE_SERVICE",
    "ApiAuthenticationFailedEvent",
    "ApiAuthorizationDeniedEvent",
    "ApiRequestCompletedEvent",
    "ApiRequestReceivedEvent",
    "CircuitBreakerOpenedEvent",
    "GatewayHealthChangedEvent",
    "QuotaExceededEvent",
    "RateLimitExceededEvent",
]
