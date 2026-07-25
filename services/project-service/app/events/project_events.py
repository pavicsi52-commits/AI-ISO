"""Project domain events.

Per docs/034 "EVENTS": ProjectCreated, ProjectUpdated, ProjectArchived,
ProjectRestored, ProjectDeleted, ProjectCloned, ProjectMemberAdded,
ProjectMemberRemoved, ProjectRoleChanged, ProjectOwnershipTransferred,
ProjectSettingsUpdated. "Integrate with Prompt 020" -- each is a
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
class ProjectCreatedEvent(DomainEvent):
    """A new project was created."""

    event_name: ClassVar[str] = "ProjectCreated"


@default_registry.register
class ProjectUpdatedEvent(DomainEvent):
    """A project's fields were updated."""

    event_name: ClassVar[str] = "ProjectUpdated"


@default_registry.register
class ProjectArchivedEvent(DomainEvent):
    """A project was archived."""

    event_name: ClassVar[str] = "ProjectArchived"


@default_registry.register
class ProjectRestoredEvent(DomainEvent):
    """A project was restored from archive."""

    event_name: ClassVar[str] = "ProjectRestored"


@default_registry.register
class ProjectDeletedEvent(DomainEvent):
    """A project was (soft-)deleted."""

    event_name: ClassVar[str] = "ProjectDeleted"


@default_registry.register
class ProjectClonedEvent(DomainEvent):
    """A project was cloned into a new one."""

    event_name: ClassVar[str] = "ProjectCloned"


@default_registry.register
class ProjectMemberAddedEvent(DomainEvent):
    """A member was added to a project."""

    event_name: ClassVar[str] = "ProjectMemberAdded"


@default_registry.register
class ProjectMemberRemovedEvent(DomainEvent):
    """A member was removed from a project."""

    event_name: ClassVar[str] = "ProjectMemberRemoved"


@default_registry.register
class ProjectRoleChangedEvent(DomainEvent):
    """A member's role on a project changed."""

    event_name: ClassVar[str] = "ProjectRoleChanged"


@default_registry.register
class ProjectOwnershipTransferredEvent(DomainEvent):
    """A project's ownership was transferred to a new owner."""

    event_name: ClassVar[str] = "ProjectOwnershipTransferred"


@default_registry.register
class ProjectSettingsUpdatedEvent(DomainEvent):
    """A project's settings were updated."""

    event_name: ClassVar[str] = "ProjectSettingsUpdated"


__all__ = [
    "ProjectArchivedEvent",
    "ProjectClonedEvent",
    "ProjectCreatedEvent",
    "ProjectDeletedEvent",
    "ProjectMemberAddedEvent",
    "ProjectMemberRemovedEvent",
    "ProjectOwnershipTransferredEvent",
    "ProjectRestoredEvent",
    "ProjectRoleChangedEvent",
    "ProjectSettingsUpdatedEvent",
    "ProjectUpdatedEvent",
]
