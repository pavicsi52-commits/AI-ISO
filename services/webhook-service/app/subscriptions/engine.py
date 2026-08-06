"""Subscription matching (docs/057 "SUBSCRIPTIONS"): does one event match
one endpoint's own subscription?

A genuine gap -- no primitive for this exists in `shared_core`. Pure and
dependency-free; the caller (``SubscriptionService``) resolves the
*candidate* subscriptions from the database, this module decides which
of them actually match a given event.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatch

from app.models.enums import SubscriptionScope


@dataclass(frozen=True, slots=True)
class SubscriptionCandidate:
    """The fields of one ``WebhookSubscription`` this engine needs to decide a match."""

    id: str
    scope: SubscriptionScope
    scope_reference: str | None
    event_types: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class EventContext:
    """The event attributes a subscription match is decided against."""

    event_type: str
    organization_id: str
    project_id: str | None = None
    role: str | None = None
    user_id: str | None = None
    topic: str | None = None
    resource_id: str | None = None


_EXACT_FIELDS: dict[SubscriptionScope, Callable[[EventContext], str | None]] = {
    SubscriptionScope.ORGANIZATION: lambda event: event.organization_id,
    SubscriptionScope.PROJECT: lambda event: event.project_id,
    SubscriptionScope.ROLE: lambda event: event.role,
    SubscriptionScope.USER: lambda event: event.user_id,
    SubscriptionScope.RESOURCE: lambda event: event.resource_id,
}
_GLOB_FIELDS: dict[SubscriptionScope, Callable[[EventContext], str]] = {
    SubscriptionScope.TOPIC: lambda event: event.topic or "",
    SubscriptionScope.EVENT: lambda event: event.event_type,
}


def _scope_matches(candidate: SubscriptionCandidate, event: EventContext) -> bool:
    """Whether *candidate*'s own scope/reference applies to *event*, ignoring its event type."""
    if candidate.scope == SubscriptionScope.WILDCARD:
        return True
    if candidate.scope == SubscriptionScope.CONDITIONAL:
        # A conditional subscription's own scope check always passes here;
        # its `condition_expression` is evaluated separately by
        # `app/filters/engine.py` against the event's full attribute set,
        # not by this module (which only knows the fixed fields above).
        return True
    if candidate.scope_reference is None:
        return False
    reference = candidate.scope_reference
    if candidate.scope in _GLOB_FIELDS:
        return fnmatch(_GLOB_FIELDS[candidate.scope](event), reference)
    getter = _EXACT_FIELDS.get(candidate.scope)
    return getter(event) == reference if getter is not None else False


def _event_type_matches(candidate: SubscriptionCandidate, event: EventContext) -> bool:
    """Whether *candidate*'s own ``event_types`` glob list matches *event*.

    An empty list matches every event type under the subscription's scope.
    """
    if not candidate.event_types:
        return True
    return any(fnmatch(event.event_type, pattern) for pattern in candidate.event_types)


def matches(candidate: SubscriptionCandidate, event: EventContext) -> bool:
    """Whether *candidate* matches *event*."""
    if not candidate.enabled:
        return False
    return _scope_matches(candidate, event) and _event_type_matches(candidate, event)


def matching_subscriptions(
    candidates: list[SubscriptionCandidate], event: EventContext
) -> list[SubscriptionCandidate]:
    """Every candidate that matches *event*, in the order given."""
    return [candidate for candidate in candidates if matches(candidate, event)]


__all__ = ["EventContext", "SubscriptionCandidate", "matches", "matching_subscriptions"]
