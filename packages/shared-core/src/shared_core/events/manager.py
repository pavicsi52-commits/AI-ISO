"""Event manager.

The primary developer-facing entry point a service actually calls,
mirroring :class:`shared_core.cache.manager.CacheManager`'s role in
Prompt 019: wires :class:`~shared_core.events.bus.EventBus`,
:class:`~shared_core.events.registry.EventRegistry`, validation, audit
logging, and metrics together behind ``publish``/``subscribe``, via a
:class:`~shared_core.events.middleware.MiddlewareChain` that validates
every event before it's published and audits/meters both directions.
"""

from __future__ import annotations

from shared_core.enums.permission import Permission
from shared_core.events.audit import audit_consume, audit_failure, audit_publish
from shared_core.events.base import BaseEvent, EventType
from shared_core.events.bus import EventBus
from shared_core.events.constants import DEFAULT_HANDLER_PRIORITY
from shared_core.events.dispatcher import EventFilter, EventHandler
from shared_core.events.metrics import measure_consume, measure_publish, record_internal_failure
from shared_core.events.middleware import MiddlewareChain
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.validator import validate_event
from shared_core.security.context import SecurityContext


class EventManager:
    """The primary developer-facing entry point for publishing and subscribing to events."""

    def __init__(
        self,
        bus: EventBus,
        *,
        registry: EventRegistry = default_registry,
        middleware: MiddlewareChain | None = None,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._middleware = middleware or _default_middleware_chain(registry)

    @property
    def middleware(self) -> MiddlewareChain:
        """The chain governing this manager's publish/subscribe pipeline."""
        return self._middleware

    async def publish(
        self,
        event: BaseEvent,
        *,
        required_permission: Permission | None = None,
        context: SecurityContext | None = None,
    ) -> None:
        """Validate, publish, meter, and audit *event*.

        Raises:
            EventValidationError: If validation fails.
            EventPublishFailedError: If the underlying publish fails after retries.
        """

        async def _terminal(evt: BaseEvent) -> None:
            validate_event(
                evt,
                registry=self._registry,
                required_permission=required_permission,
                context=context,
            )
            try:
                with measure_publish(evt.event_name):
                    await self._bus.publish(evt)
            except Exception as exc:
                if evt.event_type is EventType.INTERNAL:
                    record_internal_failure(evt.event_name)
                audit_failure(evt, error=str(exc))
                raise
            audit_publish(evt)

        await self._middleware.run_publish(event, _terminal)

    async def subscribe(
        self,
        event_name: str,
        handler: EventHandler,
        *,
        priority: int = DEFAULT_HANDLER_PRIORITY,
        filter: EventFilter | None = None,
    ) -> None:
        """Subscribe *handler* to *event_name*, wrapped with metrics and audit logging."""

        async def _wrapped(event: BaseEvent) -> None:
            async def _terminal(evt: BaseEvent) -> None:
                try:
                    with measure_consume(evt.event_name):
                        await handler(evt)
                except Exception as exc:
                    if evt.event_type is EventType.INTERNAL:
                        record_internal_failure(evt.event_name)
                    audit_failure(evt, error=str(exc))
                    raise
                audit_consume(evt)

            await self._middleware.run_consume(event, _terminal)

        await self._bus.subscribe(event_name, _wrapped, priority=priority, filter=filter)


def _default_middleware_chain(registry: EventRegistry) -> MiddlewareChain:
    """A chain whose only default behavior is validating every event before it's published.

    ``EventManager.publish`` already calls :func:`~shared_core.events.validator.validate_event`
    directly in its terminal step, so this default chain starts empty --
    callers extend it via :attr:`EventManager.middleware` for
    cross-cutting concerns beyond what's built in (e.g. tracing, extra
    logging), keeping the built-in validate/meter/audit behavior as the
    always-on baseline rather than something a middleware could
    accidentally skip.
    """
    return MiddlewareChain()


__all__ = ["EventManager"]
