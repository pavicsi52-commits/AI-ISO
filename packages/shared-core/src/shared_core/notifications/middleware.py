"""Dispatch middleware.

Per docs/025_Enterprise_Notification_Framework.md.txt "SECURITY": Mask
Sensitive Data, Audit Notifications, Prevent Duplicate Delivery. A
middleware chain wrapping
:meth:`shared_core.notifications.dispatcher.NotificationDispatcher.dispatch`
-- each middleware decides whether to call ``next_handler`` at all
(enabling short-circuiting, e.g. for duplicate suppression) and can
inspect/transform the result.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.logging.logger import get_logger
from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.helpers import mask_sensitive_metadata

logger = get_logger("shared_core.notifications")

DispatchHandler = Callable[[NotificationMessage], Awaitable[DeliveryResult]]
DispatchMiddleware = Callable[[NotificationMessage, DispatchHandler], Awaitable[DeliveryResult]]


def apply_middleware(
    handler: DispatchHandler, middlewares: list[DispatchMiddleware]
) -> DispatchHandler:
    """Wrap *handler* in every middleware, outermost first ("the chain")."""
    for middleware in reversed(middlewares):
        handler = _bind(middleware, handler)
    return handler


def _bind(middleware: DispatchMiddleware, next_handler: DispatchHandler) -> DispatchHandler:
    async def wrapped(message: NotificationMessage) -> DeliveryResult:
        return await middleware(message, next_handler)

    return wrapped


async def audit_logging_middleware(
    message: NotificationMessage, next_handler: DispatchHandler
) -> DeliveryResult:
    """Audit-log every dispatch attempt, with sensitive metadata masked ("Audit Notifications")."""
    result = await next_handler(message)
    logger.audit(
        "notification.dispatch",
        resource=message.notification_id,
        outcome=result.status.value,
        channel=message.channel.value,
        notification_type=message.notification_type.value,
        metadata=mask_sensitive_metadata(message.metadata),
    )
    return result


class DuplicateSuppressionMiddleware:
    """Suppresses re-sending a notification ID already dispatched ("Prevent Duplicate Delivery")."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def __call__(
        self, message: NotificationMessage, next_handler: DispatchHandler
    ) -> DeliveryResult:
        if message.notification_id in self._seen:
            return build_delivery_result(
                status=DeliveryStatus.CANCELLED,
                channel=message.channel,
                error="Duplicate notification_id; already dispatched.",
            )
        self._seen.add(message.notification_id)
        return await next_handler(message)


__all__ = [
    "DispatchHandler",
    "DispatchMiddleware",
    "DuplicateSuppressionMiddleware",
    "apply_middleware",
    "audit_logging_middleware",
]
