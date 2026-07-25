"""In-process event dispatch.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT DISPATCHER": Route
to Handler, Multiple Handlers, Handler Priority, Handler Filtering,
Handler Registration. Also the structural home of "INTERNAL EVENTS...
Never leave the owning service" (docs/020): :mod:`shared_core.events.bus`
routes :class:`~shared_core.events.base.InternalEvent` through this
dispatcher exclusively, never through the queue-backed publisher, so
there is no code path here that touches the network.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared_core.events.base import BaseEvent
from shared_core.events.constants import DEFAULT_HANDLER_PRIORITY

EventHandler = Callable[[BaseEvent], Awaitable[None]]
EventFilter = Callable[[BaseEvent], bool]


@dataclass(frozen=True, slots=True)
class HandlerRegistration:
    """One handler registered for one event name, with its priority and optional filter."""

    handler: EventHandler
    priority: int = DEFAULT_HANDLER_PRIORITY
    filter: EventFilter | None = None

    def accepts(self, event: BaseEvent) -> bool:
        """Return whether this registration's filter (if any) accepts *event*."""
        return self.filter is None or self.filter(event)


@dataclass(slots=True)
class EventDispatcher:
    """Dispatches an event to every registered handler for its ``event_name``, priority order first.

    Multiple handlers per event name are supported ("Multiple Handlers");
    each runs regardless of whether an earlier one raised, and every
    exception is collected and re-raised together so no failure is
    silently swallowed.
    """

    _handlers: dict[str, list[HandlerRegistration]] = field(default_factory=dict)

    def register(
        self,
        event_name: str,
        handler: EventHandler,
        *,
        priority: int = DEFAULT_HANDLER_PRIORITY,
        filter: EventFilter | None = None,
    ) -> None:
        """Register *handler* for *event_name*. Lower *priority* runs first ("Handler Priority")."""
        registrations = self._handlers.setdefault(event_name, [])
        registrations.append(HandlerRegistration(handler=handler, priority=priority, filter=filter))
        registrations.sort(key=lambda reg: reg.priority)

    def unregister(self, event_name: str, handler: EventHandler) -> None:
        """Remove *handler* from *event_name*'s registrations, if present."""
        registrations = self._handlers.get(event_name)
        if not registrations:
            return
        self._handlers[event_name] = [reg for reg in registrations if reg.handler is not handler]

    def handlers_for(self, event_name: str) -> list[HandlerRegistration]:
        """Return every registration for *event_name*, priority order."""
        return list(self._handlers.get(event_name, []))

    async def dispatch(self, event: BaseEvent) -> int:
        """Run every matching, filter-accepting handler for *event* in priority order.

        Returns:
            The number of handlers actually invoked.

        Raises:
            ExceptionGroup: If one or more handlers raised. Every handler
                still runs; failures are collected, not short-circuited.
        """
        registrations = [reg for reg in self.handlers_for(event.event_name) if reg.accepts(event)]
        errors: list[Exception] = []
        invoked = 0
        for registration in registrations:
            try:
                await registration.handler(event)
                invoked += 1
            except Exception as exc:
                errors.append(exc)
        if errors:
            message = f"{len(errors)} handler(s) failed for '{event.event_name}'."
            raise ExceptionGroup(message, errors)
        return invoked


__all__ = ["EventDispatcher", "EventFilter", "EventHandler", "HandlerRegistration"]
