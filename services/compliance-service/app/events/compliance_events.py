"""Domain events this service publishes (docs/051 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every compliance write raises and the caller gets a 400 for a request
that did nothing wrong.

**No event is published per result.** An assessment produces one result
per control per target, which for a real estate is millions of rows per
run. An event each would be a firehose nobody could subscribe to and
would cost more to carry than the assessment costs to compute. What
subscribers actually want is the exceptional case and the summary, so
``ComplianceViolationDetected`` fires per *finding* -- which is
deduplicated by fingerprint -- and ``ComplianceAssessmentCompleted``
carries the totals.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "compliance-service"


@default_registry.register
class ComplianceAssessmentStartedEvent(DomainEvent):
    """An assessment run began."""

    event_name: ClassVar[str] = "ComplianceAssessmentStarted"


@default_registry.register
class ComplianceAssessmentCompletedEvent(DomainEvent):
    """An assessment run finished, with its totals.

    Carries the counts rather than the results. A subscriber that wants
    detail can read it; a subscriber that wants to know whether posture
    moved should not have to.
    """

    event_name: ClassVar[str] = "ComplianceAssessmentCompleted"


@default_registry.register
class ComplianceViolationDetectedEvent(DomainEvent):
    """A control is not being met.

    Fired per finding, so a re-detection of the same problem on the same
    target does not fire again -- the fingerprint is what makes that
    true, and without it a daily assessment would emit the same event
    365 times a year per host.
    """

    event_name: ClassVar[str] = "ComplianceViolationDetected"


@default_registry.register
class ComplianceScoreUpdatedEvent(DomainEvent):
    """A compliance score was recomputed."""

    event_name: ClassVar[str] = "ComplianceScoreUpdated"


@default_registry.register
class ComplianceExceptionCreatedEvent(DomainEvent):
    """A waiver was requested or approved."""

    event_name: ClassVar[str] = "ComplianceExceptionCreated"


@default_registry.register
class RiskRegisteredEvent(DomainEvent):
    """A risk entered the register."""

    event_name: ClassVar[str] = "RiskRegistered"


@default_registry.register
class EvidenceCollectedEvent(DomainEvent):
    """Proof was recorded.

    Carries the digest, not the payload. Evidence can be megabytes and
    can contain exactly the configuration detail an organization is
    least willing to broadcast; the digest is what a subscriber needs to
    confirm it is talking about the same artefact.
    """

    event_name: ClassVar[str] = "EvidenceCollected"


@default_registry.register
class RemediationCompletedEvent(DomainEvent):
    """A fix was applied and verified."""

    event_name: ClassVar[str] = "RemediationCompleted"


__all__ = [
    "SOURCE_SERVICE",
    "ComplianceAssessmentCompletedEvent",
    "ComplianceAssessmentStartedEvent",
    "ComplianceExceptionCreatedEvent",
    "ComplianceScoreUpdatedEvent",
    "ComplianceViolationDetectedEvent",
    "EvidenceCollectedEvent",
    "RemediationCompletedEvent",
    "RiskRegisteredEvent",
]
