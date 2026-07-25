"""Event decorators.

``@event_handler`` only *marks* a function (attaching the event name it
wants to handle); it can't subscribe on its own because subscribing is
async and this decorator runs synchronously at import time. Pass every
decorated function to :func:`register_handlers` at service startup to
actually wire the subscriptions -- the same "mark now, wire later"
pattern route decorators use in typical async web frameworks.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from typing import TypeVar

from shared_core.events.base import BaseEvent
from shared_core.events.manager import EventManager

EventHandlerFn = Callable[[BaseEvent], Awaitable[None]]
_EVENT_NAME_ATTR = "__event_name__"

T = TypeVar("T", bound=BaseEvent)
PublisherFn = Callable[..., Awaitable[T]]


def event_handler(event_name: str) -> Callable[[EventHandlerFn], EventHandlerFn]:
    """Mark the decorated async function as a handler for *event_name*.

    Doesn't subscribe by itself -- see :func:`register_handlers`.
    """

    def decorator(handler: EventHandlerFn) -> EventHandlerFn:
        setattr(handler, _EVENT_NAME_ATTR, event_name)
        return handler

    return decorator


def get_event_name(handler: EventHandlerFn) -> str | None:
    """Return the event name *handler* was decorated with, or ``None`` if it wasn't."""
    name = getattr(handler, _EVENT_NAME_ATTR, None)
    return name if isinstance(name, str) else None


async def register_handlers(manager: EventManager, handlers: Iterable[EventHandlerFn]) -> None:
    """Subscribe every ``@event_handler``-decorated function in *handlers* to its event name.

    Functions in *handlers* that weren't decorated with ``@event_handler``
    are skipped.
    """
    for handler in handlers:
        event_name = get_event_name(handler)
        if event_name is None:
            continue
        await manager.subscribe(event_name, handler)


def publishes(manager: EventManager) -> Callable[[PublisherFn[T]], PublisherFn[T]]:
    """Automatically publish the wrapped async function's returned event after it succeeds."""

    def decorator(func: PublisherFn[T]) -> PublisherFn[T]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            event = await func(*args, **kwargs)
            await manager.publish(event)
            return event

        return wrapper

    return decorator


__all__ = ["event_handler", "get_event_name", "publishes", "register_handlers"]
