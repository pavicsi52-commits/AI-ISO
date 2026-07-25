"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

import uuid


def generate_message_id() -> str:
    """Generate a new unique message ID (the MESSAGE FORMAT's ``message_id`` field)."""
    return str(uuid.uuid4())


def queue_name_for(*segments: str) -> str:
    """Join *segments* into a dot-separated queue name (e.g. ``"automation.discovery"``).

    Raises:
        ValueError: If no segments are given.
    """
    if not segments:
        raise ValueError("queue_name_for() requires at least one segment.")
    return ".".join(segments)


__all__ = ["generate_message_id", "queue_name_for"]
