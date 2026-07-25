"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

import uuid


def generate_correlation_id() -> str:
    """Generate a new correlation ID for a causally-related chain of events."""
    return str(uuid.uuid4())


def event_name_from_class(cls: type) -> str:
    """Derive a default event name from a class's own name.

    Per docs/020_Enterprise_Event_Framework.md.txt "EVENT NAMING": past
    tense, matching the class name itself is the natural default (e.g.
    class ``UserCreated`` -> event name ``"UserCreated"``) -- callers who
    want a different/dotted/namespaced name still set ``event_name``
    explicitly on their subclass.
    """
    return cls.__name__


__all__ = ["event_name_from_class", "generate_correlation_id"]
