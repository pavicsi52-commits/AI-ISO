"""Shared type aliases for this service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EventPublisher = Callable[[Any], Awaitable[None]]
"""How a service announces a domain event.

A callable rather than the publisher class, so a test can pass a
recording function and exercise the real publish path instead of
stubbing it out.
"""

__all__ = ["EventPublisher"]
