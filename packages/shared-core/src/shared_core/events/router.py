"""Event routing.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT ROUTING": Route by
Event Type, Route by Pattern, Content-Based Routing, Fan-Out, Conditional
Routing. A small, generic glob-pattern router -- kept separate from
:mod:`shared_core.events.dispatcher` (which decides which *handlers* run
for a resolved target) so a single router can also route to things that
aren't handlers, e.g. resolving an event name to the queue(s) it fans out
to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

RouteCondition = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class Route[T]:
    """One pattern -> target mapping, with an optional predicate for content-based routing."""

    pattern: str
    target: T
    condition: RouteCondition | None = None


@dataclass(slots=True)
class EventRouter[T]:
    """Resolves an event name to every matching route's target(s) ("Fan-Out").

    Patterns use shell-style globbing (``fnmatch``), e.g. ``"User*"``
    matches ``UserCreated`` and ``UserDeleted``; ``"*"`` matches anything.
    Routes are evaluated in registration order.
    """

    _routes: list[Route[T]] = field(default_factory=list)

    def add_route(
        self, pattern: str, target: T, *, condition: RouteCondition | None = None
    ) -> None:
        """Register a pattern -> target route. "Route by Pattern" / "Conditional Routing"."""
        self._routes.append(Route(pattern=pattern, target=target, condition=condition))

    def resolve(self, event_name: str) -> list[T]:
        """Return every route's target whose pattern (and condition) matches *event_name*."""
        return [
            route.target
            for route in self._routes
            if fnmatchcase(event_name, route.pattern)
            and (route.condition is None or route.condition(event_name))
        ]

    def matches_any(self, event_name: str) -> bool:
        """Return whether at least one route matches *event_name*."""
        return len(self.resolve(event_name)) > 0

    def clear(self) -> None:
        """Remove every registered route."""
        self._routes.clear()


__all__ = ["EventRouter", "Route", "RouteCondition"]
