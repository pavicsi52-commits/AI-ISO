"""Domain events this service publishes (docs/050 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020).

**``PolicyEvaluated`` is deliberately not published per decision.** This
service answers every protected operation on the platform, so an event
per decision would be an event per action anywhere -- a firehose that
would cost more to carry than the decisions cost to make, and that
nobody could subscribe to usefully. What subscribers actually want is
the exceptional case, so ``PolicyDenied`` fires on a refusal and the
rest is available in the decision log and the statistics rollup.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "policy-engine-service"


class PolicyCreatedEvent(DomainEvent):
    """A policy was authored."""

    event_name: ClassVar[str] = "PolicyCreated"


class PolicyUpdatedEvent(DomainEvent):
    """A policy's metadata changed.

    Note this does *not* mean live authorization changed -- only
    publishing does that.
    """

    event_name: ClassVar[str] = "PolicyUpdated"


class PolicyPublishedEvent(DomainEvent):
    """A policy became live.

    The one event a decision cache must react to. Everything else can be
    picked up on the next poll; this cannot, because the window between
    publishing a deny and it taking effect is a window in which the
    estate is governed by yesterday's rules.
    """

    event_name: ClassVar[str] = "PolicyPublished"


class PolicyEvaluatedEvent(DomainEvent):
    """A decision was made.

    Defined because docs/050 names it, and published only for
    explicitly-requested traces rather than for every decision -- see
    this module's docstring.
    """

    event_name: ClassVar[str] = "PolicyEvaluated"


class PolicyDeniedEvent(DomainEvent):
    """A request was refused."""

    event_name: ClassVar[str] = "PolicyDenied"


class PolicyApprovedEvent(DomainEvent):
    """An approval obligation was satisfied."""

    event_name: ClassVar[str] = "PolicyApproved"


class PolicyViolationDetectedEvent(DomainEvent):
    """A compliance rule was broken."""

    event_name: ClassVar[str] = "PolicyViolationDetected"


class QuotaExceededEvent(DomainEvent):
    """A consumption budget was exhausted."""

    event_name: ClassVar[str] = "QuotaExceeded"


class SimulationCompletedEvent(DomainEvent):
    """A policy simulation finished."""

    event_name: ClassVar[str] = "SimulationCompleted"


__all__ = [
    "SOURCE_SERVICE",
    "PolicyApprovedEvent",
    "PolicyCreatedEvent",
    "PolicyDeniedEvent",
    "PolicyEvaluatedEvent",
    "PolicyPublishedEvent",
    "PolicyUpdatedEvent",
    "PolicyViolationDetectedEvent",
    "QuotaExceededEvent",
    "SimulationCompletedEvent",
]
