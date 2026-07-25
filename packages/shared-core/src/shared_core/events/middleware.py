"""Event middleware.

Per docs/020_Enterprise_Event_Framework.md.txt "EVENT DISPATCHER" and the
framework's overall pipeline shape (validate/audit/meter around every
publish and consume): an onion-style chain of hooks that run around the
actual publish/consume call, the same shape as
:mod:`shared_core.middleware`'s HTTP middleware chain (Prompt 012) but
for events instead of requests.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared_core.events.base import BaseEvent

Next = Callable[[BaseEvent], Awaitable[None]]
Middleware = Callable[[BaseEvent, Next], Awaitable[None]]
PublishMiddleware = Middleware
ConsumeMiddleware = Middleware


@dataclass(slots=True)
class MiddlewareChain:
    """An ordered chain of publish/consume middleware, run onion-style around a terminal action.

    The first-registered middleware is outermost: it runs first on the
    way in and last on the way out. A middleware may replace the event it
    passes to ``next`` (e.g. to attach masked/compacted data), and that
    replacement is what every subsequent middleware and the terminal
    action sees.
    """

    _publish_middleware: list[PublishMiddleware] = field(default_factory=list)
    _consume_middleware: list[ConsumeMiddleware] = field(default_factory=list)

    def use_publish(self, middleware: PublishMiddleware) -> None:
        """Register a middleware to run around every publish."""
        self._publish_middleware.append(middleware)

    def use_consume(self, middleware: ConsumeMiddleware) -> None:
        """Register a middleware to run around every consume."""
        self._consume_middleware.append(middleware)

    async def run_publish(self, event: BaseEvent, terminal: Next) -> None:
        """Run every registered publish middleware around *terminal*, then invoke *terminal*."""
        await self._run(event, terminal, self._publish_middleware)

    async def run_consume(self, event: BaseEvent, terminal: Next) -> None:
        """Run every registered consume middleware around *terminal*, then invoke *terminal*."""
        await self._run(event, terminal, self._consume_middleware)

    @staticmethod
    async def _run(event: BaseEvent, terminal: Next, chain: list[Middleware]) -> None:
        async def build(index: int, evt: BaseEvent) -> None:
            if index >= len(chain):
                await terminal(evt)
                return

            async def call_next(next_evt: BaseEvent, _index: int = index) -> None:
                await build(_index + 1, next_evt)

            await chain[index](evt, call_next)

        await build(0, event)


__all__ = ["ConsumeMiddleware", "MiddlewareChain", "PublishMiddleware"]
