"""Playbook service domain events.

Per docs/041 "EVENTS": PlaybookCreated, PlaybookUpdated,
PlaybookApproved, PlaybookRejected, PlaybookPublished,
PlaybookDeprecated, PlaybookArchived, VersionCreated,
ValidationCompleted, SignatureVerified. "Integrate with Prompt 020" --
each is a :class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`. Registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class PlaybookCreatedEvent(DomainEvent):
    """A new playbook was created."""

    event_name: ClassVar[str] = "PlaybookCreated"


@default_registry.register
class PlaybookUpdatedEvent(DomainEvent):
    """A playbook's own metadata was updated."""

    event_name: ClassVar[str] = "PlaybookUpdated"


@default_registry.register
class PlaybookApprovedEvent(DomainEvent):
    """A playbook approval gate was approved."""

    event_name: ClassVar[str] = "PlaybookApproved"


@default_registry.register
class PlaybookRejectedEvent(DomainEvent):
    """A playbook approval gate was rejected."""

    event_name: ClassVar[str] = "PlaybookRejected"


@default_registry.register
class PlaybookPublishedEvent(DomainEvent):
    """A playbook was published."""

    event_name: ClassVar[str] = "PlaybookPublished"


@default_registry.register
class PlaybookDeprecatedEvent(DomainEvent):
    """A playbook was deprecated."""

    event_name: ClassVar[str] = "PlaybookDeprecated"


@default_registry.register
class PlaybookArchivedEvent(DomainEvent):
    """A playbook was archived."""

    event_name: ClassVar[str] = "PlaybookArchived"


@default_registry.register
class VersionCreatedEvent(DomainEvent):
    """A new playbook version snapshot was created."""

    event_name: ClassVar[str] = "VersionCreated"


@default_registry.register
class ValidationCompletedEvent(DomainEvent):
    """A playbook content validation run completed."""

    event_name: ClassVar[str] = "ValidationCompleted"


@default_registry.register
class SignatureVerifiedEvent(DomainEvent):
    """A playbook version's digital signature was verified."""

    event_name: ClassVar[str] = "SignatureVerified"


__all__ = [
    "PlaybookApprovedEvent",
    "PlaybookArchivedEvent",
    "PlaybookCreatedEvent",
    "PlaybookDeprecatedEvent",
    "PlaybookPublishedEvent",
    "PlaybookRejectedEvent",
    "PlaybookUpdatedEvent",
    "SignatureVerifiedEvent",
    "ValidationCompletedEvent",
    "VersionCreatedEvent",
]
