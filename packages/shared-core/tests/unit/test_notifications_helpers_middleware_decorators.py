"""Tests for helpers.py, middleware.py, and decorators.py."""

from __future__ import annotations

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.channels import (
    ChannelRegistry,
    NotificationMessage,
    build_notification,
)
from shared_core.notifications.decorators import notify_on_failure
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.helpers import mask_email, mask_sensitive_metadata, truncate
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.middleware import (
    DuplicateSuppressionMiddleware,
    apply_middleware,
    audit_logging_middleware,
)
from shared_core.notifications.retry import DeadLetterStore

# --- helpers.py ---


def test_mask_sensitive_metadata_masks_matching_keys() -> None:
    masked = mask_sensitive_metadata({"api_key": "sk-live-123", "user_id": "user-1"})

    assert masked["api_key"] == "***MASKED***"
    assert masked["user_id"] == "user-1"


def test_truncate_leaves_short_text_unchanged() -> None:
    assert truncate("hello", max_length=10) == "hello"


def test_truncate_shortens_long_text_with_an_ellipsis() -> None:
    result = truncate("hello world", max_length=6)

    assert result == "hello…"
    assert len(result) == 6


def test_mask_email_keeps_the_domain_visible() -> None:
    assert mask_email("ada@example.com") == "a***@example.com"


def test_mask_email_handles_a_malformed_address() -> None:
    assert mask_email("not-an-email") == "***MASKED***"


# --- middleware.py ---


async def test_audit_logging_middleware_passes_through_the_result() -> None:
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )
    expected = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    async def handler(_message: NotificationMessage) -> DeliveryResult:
        return expected

    result = await audit_logging_middleware(message, handler)

    assert result is expected


async def test_duplicate_suppression_middleware_blocks_a_repeat_notification_id() -> None:
    middleware = DuplicateSuppressionMiddleware()
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )
    calls = 0

    async def handler(_message: NotificationMessage) -> DeliveryResult:
        nonlocal calls
        calls += 1
        return build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    first = await middleware(message, handler)
    second = await middleware(message, handler)

    assert first.status == DeliveryStatus.SENT
    assert second.status == DeliveryStatus.CANCELLED
    assert calls == 1


async def test_apply_middleware_chains_in_outermost_first_order() -> None:
    order: list[str] = []

    async def first(message: NotificationMessage, next_handler):  # type: ignore[no-untyped-def]
        order.append("first-before")
        result = await next_handler(message)
        order.append("first-after")
        return result

    async def second(message: NotificationMessage, next_handler):  # type: ignore[no-untyped-def]
        order.append("second-before")
        result = await next_handler(message)
        order.append("second-after")
        return result

    async def base_handler(_message: NotificationMessage) -> DeliveryResult:
        order.append("base")
        return build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    chained = apply_middleware(base_handler, [first, second])
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    await chained(message)

    assert order == ["first-before", "second-before", "base", "second-after", "first-after"]


# --- decorators.py ---


class _AlwaysSucceedsChannel:
    channel_type = NotificationChannel.EMAIL

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        return build_delivery_result(status=DeliveryStatus.SENT, channel=self.channel_type)


def _dispatcher() -> NotificationDispatcher:
    channels = ChannelRegistry()
    channels.register(_AlwaysSucceedsChannel())
    return NotificationDispatcher(
        channels=channels, history=HistoryStore(), dead_letters=DeadLetterStore()
    )


async def test_notify_on_failure_dispatches_a_notification_and_reraises() -> None:
    dispatcher = _dispatcher()

    @notify_on_failure(dispatcher, channel=NotificationChannel.EMAIL, user_id="user-1")
    async def do_work() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await do_work()

    entries = dispatcher._history.entries()
    assert len(entries) == 1
    assert entries[0].result.status == DeliveryStatus.SENT


async def test_notify_on_failure_does_not_dispatch_on_success() -> None:
    dispatcher = _dispatcher()

    @notify_on_failure(dispatcher, channel=NotificationChannel.EMAIL, user_id="user-1")
    async def do_work() -> str:
        return "done"

    result = await do_work()

    assert result == "done"
    assert dispatcher._history.entries() == []


async def test_notify_on_failure_uses_a_custom_body_builder() -> None:
    dispatcher = _dispatcher()
    captured_bodies: list[str] = []

    class _CapturingChannel:
        channel_type = NotificationChannel.EMAIL

        async def send(self, message: NotificationMessage) -> DeliveryResult:
            captured_bodies.append(message.body)
            return build_delivery_result(status=DeliveryStatus.SENT, channel=self.channel_type)

    channels = ChannelRegistry()
    channels.register(_CapturingChannel())
    dispatcher = NotificationDispatcher(
        channels=channels, history=HistoryStore(), dead_letters=DeadLetterStore()
    )

    @notify_on_failure(
        dispatcher,
        channel=NotificationChannel.EMAIL,
        user_id="user-1",
        body_builder=lambda exc: f"custom: {exc}",
    )
    async def do_work() -> None:
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        await do_work()

    assert captured_bodies == ["custom: bad input"]
