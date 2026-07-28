"""Monitoring service domain events.

Per docs/044 "EVENTS": MetricCollected, HealthChanged,
AvailabilityChanged, ThresholdExceeded, ThresholdRecovered,
SyntheticTestFailed, DependencyChanged, SLOViolated, SLAViolated.
"Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`, registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class MetricCollectedEvent(DomainEvent):
    """A metric data point was collected and persisted."""

    event_name: ClassVar[str] = "MetricCollected"


@default_registry.register
class HealthChangedEvent(DomainEvent):
    """A target's own overall health status changed."""

    event_name: ClassVar[str] = "HealthChanged"


@default_registry.register
class AvailabilityChangedEvent(DomainEvent):
    """A target's own availability status changed."""

    event_name: ClassVar[str] = "AvailabilityChanged"


@default_registry.register
class ThresholdExceededEvent(DomainEvent):
    """A collected metric value breached a configured threshold."""

    event_name: ClassVar[str] = "ThresholdExceeded"


@default_registry.register
class ThresholdRecoveredEvent(DomainEvent):
    """A previously breached metric value returned within its own threshold."""

    event_name: ClassVar[str] = "ThresholdRecovered"


@default_registry.register
class SyntheticTestFailedEvent(DomainEvent):
    """A scheduled synthetic check failed."""

    event_name: ClassVar[str] = "SyntheticTestFailed"


@default_registry.register
class DependencyChangedEvent(DomainEvent):
    """A target dependency graph edge was created or changed."""

    event_name: ClassVar[str] = "DependencyChanged"


@default_registry.register
class SLOViolatedEvent(DomainEvent):
    """A Service Level Objective was violated."""

    event_name: ClassVar[str] = "SLOViolated"


@default_registry.register
class SLAViolatedEvent(DomainEvent):
    """A Service Level Agreement was violated."""

    event_name: ClassVar[str] = "SLAViolated"


__all__ = [
    "AvailabilityChangedEvent",
    "DependencyChangedEvent",
    "HealthChangedEvent",
    "MetricCollectedEvent",
    "SLAViolatedEvent",
    "SLOViolatedEvent",
    "SyntheticTestFailedEvent",
    "ThresholdExceededEvent",
    "ThresholdRecoveredEvent",
]
