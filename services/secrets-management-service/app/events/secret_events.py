"""Secrets management domain events.

Per docs/035 "EVENTS": SecretCreated, SecretUpdated, SecretDeleted,
SecretRotated, SecretExpired, SecretAccessed, CertificateImported,
CertificateExpired, KeyGenerated, KeyRevoked, LeaseCreated,
LeaseExpired. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
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
class SecretCreatedEvent(DomainEvent):
    """A new secret was created."""

    event_name: ClassVar[str] = "SecretCreated"


@default_registry.register
class SecretUpdatedEvent(DomainEvent):
    """A secret's identity/lifecycle fields were updated."""

    event_name: ClassVar[str] = "SecretUpdated"


@default_registry.register
class SecretDeletedEvent(DomainEvent):
    """A secret was (soft-)deleted."""

    event_name: ClassVar[str] = "SecretDeleted"


@default_registry.register
class SecretRotatedEvent(DomainEvent):
    """A secret's value was rotated to a new version."""

    event_name: ClassVar[str] = "SecretRotated"


@default_registry.register
class SecretExpiredEvent(DomainEvent):
    """A secret passed its expiration time."""

    event_name: ClassVar[str] = "SecretExpired"


@default_registry.register
class SecretAccessedEvent(DomainEvent):
    """A secret's decrypted value was read."""

    event_name: ClassVar[str] = "SecretAccessed"


@default_registry.register
class CertificateImportedEvent(DomainEvent):
    """A certificate was imported into the store."""

    event_name: ClassVar[str] = "CertificateImported"


@default_registry.register
class CertificateExpiredEvent(DomainEvent):
    """A certificate passed its expiration time."""

    event_name: ClassVar[str] = "CertificateExpired"


@default_registry.register
class KeyGeneratedEvent(DomainEvent):
    """A new Data Encryption Key was generated."""

    event_name: ClassVar[str] = "KeyGenerated"


@default_registry.register
class KeyRevokedEvent(DomainEvent):
    """A Data Encryption Key was revoked."""

    event_name: ClassVar[str] = "KeyRevoked"


@default_registry.register
class LeaseCreatedEvent(DomainEvent):
    """A temporary-credential lease was issued."""

    event_name: ClassVar[str] = "LeaseCreated"


@default_registry.register
class LeaseExpiredEvent(DomainEvent):
    """A lease passed its expiration time."""

    event_name: ClassVar[str] = "LeaseExpired"


__all__ = [
    "CertificateExpiredEvent",
    "CertificateImportedEvent",
    "KeyGeneratedEvent",
    "KeyRevokedEvent",
    "LeaseCreatedEvent",
    "LeaseExpiredEvent",
    "SecretAccessedEvent",
    "SecretCreatedEvent",
    "SecretDeletedEvent",
    "SecretExpiredEvent",
    "SecretRotatedEvent",
    "SecretUpdatedEvent",
]
