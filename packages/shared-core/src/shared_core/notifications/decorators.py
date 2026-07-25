"""Notification decorators."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.channels import build_notification
from shared_core.notifications.dispatcher import NotificationDispatcher

P = ParamSpec("P")
T = TypeVar("T")

BodyBuilder = Callable[[BaseException], str]


def _default_body_builder(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def notify_on_failure(
    dispatcher: NotificationDispatcher,
    *,
    channel: NotificationChannel,
    user_id: str,
    notification_type: NotificationType = NotificationType.ERROR,
    priority: Priority = Priority.HIGH,
    subject: str | None = None,
    body_builder: BodyBuilder = _default_body_builder,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Dispatch a notification if the wrapped function raises, then re-raise ("@notify_on_failure").

    The wrapped function's own exception always propagates unchanged --
    a failure to *notify about* a failure must never mask the original one.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                message = build_notification(
                    channel=channel,
                    notification_type=notification_type,
                    priority=priority,
                    body=body_builder(exc),
                    user_id=user_id,
                    subject=subject or f"{func.__name__} failed",
                )
                await dispatcher.dispatch(message)
                raise

        return wrapper

    return decorator


__all__ = ["notify_on_failure"]
