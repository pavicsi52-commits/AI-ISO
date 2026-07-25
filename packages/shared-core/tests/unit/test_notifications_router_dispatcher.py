"""Tests for router.py and dispatcher.py."""

from __future__ import annotations

from datetime import time

from shared_core.cache.ratelimit import RateLimitStatus
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.channels import (
    ChannelRegistry,
    NotificationMessage,
    build_notification,
)
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.preferences import NotificationPreferences, PreferencesStore
from shared_core.notifications.retry import DeadLetterStore, RetryPolicy
from shared_core.notifications.router import NotificationRouter


class _ScriptedChannel:
    """A stub channel returning a pre-scripted sequence of results, one per call."""

    def __init__(self, channel_type: NotificationChannel, results: list[DeliveryResult]):
        self.channel_type = channel_type
        self._results = list(results)
        self.calls = 0

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        self.calls += 1
        return self._results[min(self.calls, len(self._results)) - 1]


def _fast_retry_policy(max_attempts: int) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts, backoff_base_seconds=0.001, backoff_max_seconds=0.01
    )


# --- router.py ---


def test_router_resolves_the_requested_channel_when_allowed() -> None:
    store = PreferencesStore()
    router = NotificationRouter(store)

    channels = router.resolve_channels(
        "user-1",
        notification_type=NotificationType.INFORMATION,
        requested_channel=NotificationChannel.SLACK,
    )

    assert channels == [NotificationChannel.SLACK]


def test_router_returns_no_channels_when_the_requested_channel_is_unsubscribed() -> None:
    store = PreferencesStore()
    store.unsubscribe("user-1", NotificationChannel.SLACK)
    router = NotificationRouter(store)

    channels = router.resolve_channels(
        "user-1",
        notification_type=NotificationType.INFORMATION,
        requested_channel=NotificationChannel.SLACK,
    )

    assert channels == []


def test_router_falls_back_to_preferred_channels_with_no_explicit_request() -> None:
    store = PreferencesStore()
    store.set(
        NotificationPreferences(
            user_id="user-1",
            preferred_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        )
    )
    router = NotificationRouter(store)

    channels = router.resolve_channels("user-1", notification_type=NotificationType.INFORMATION)

    assert channels == [NotificationChannel.EMAIL, NotificationChannel.SLACK]


def test_router_orders_resolved_channels_by_channel_priority() -> None:
    store = PreferencesStore()
    store.set(
        NotificationPreferences(
            user_id="user-1",
            preferred_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
            channel_priority=[NotificationChannel.SLACK, NotificationChannel.EMAIL],
        )
    )
    router = NotificationRouter(store)

    channels = router.resolve_channels("user-1", notification_type=NotificationType.INFORMATION)

    assert channels == [NotificationChannel.SLACK, NotificationChannel.EMAIL]


def test_router_should_defer_for_quiet_hours_respects_the_window() -> None:
    store = PreferencesStore()
    store.set(
        NotificationPreferences(
            user_id="user-1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
    )
    router = NotificationRouter(store)

    assert (
        router.should_defer_for_quiet_hours("user-1", priority=Priority.NORMAL, now=time(23, 0))
        is True
    )
    assert (
        router.should_defer_for_quiet_hours("user-1", priority=Priority.NORMAL, now=time(12, 0))
        is False
    )


def test_router_critical_priority_overrides_quiet_hours() -> None:
    store = PreferencesStore()
    store.set(
        NotificationPreferences(
            user_id="user-1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
    )
    router = NotificationRouter(store)

    assert (
        router.should_defer_for_quiet_hours("user-1", priority=Priority.CRITICAL, now=time(23, 0))
        is False
    )


# --- dispatcher.py ---


async def test_dispatcher_records_a_successful_send_on_the_first_attempt() -> None:
    channels = ChannelRegistry()
    result = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)
    channels.register(_ScriptedChannel(NotificationChannel.EMAIL, [result]))
    history = HistoryStore()
    dispatcher = NotificationDispatcher(
        channels=channels, history=history, dead_letters=DeadLetterStore()
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    outcome = await dispatcher.dispatch(message)

    assert outcome.status == DeliveryStatus.SENT
    assert message.status == DeliveryStatus.SENT
    assert message.sent_at is not None
    assert len(history.for_notification(message.notification_id)) == 1


async def test_dispatcher_retries_a_transient_failure_then_succeeds() -> None:
    channels = ChannelRegistry()
    failure = build_delivery_result(
        status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL, error="timeout"
    )
    success = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)
    stub = _ScriptedChannel(NotificationChannel.EMAIL, [failure, success])
    channels.register(stub)
    history = HistoryStore()
    dispatcher = NotificationDispatcher(
        channels=channels,
        history=history,
        dead_letters=DeadLetterStore(),
        retry_policy=_fast_retry_policy(3),
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    outcome = await dispatcher.dispatch(message)

    assert outcome.status == DeliveryStatus.SENT
    assert stub.calls == 2
    assert len(history.for_notification(message.notification_id)) == 2


async def test_dispatcher_dead_letters_after_exhausting_retries() -> None:
    channels = ChannelRegistry()
    failure = build_delivery_result(
        status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL, error="down"
    )
    channels.register(_ScriptedChannel(NotificationChannel.EMAIL, [failure]))
    dead_letters = DeadLetterStore()
    dispatcher = NotificationDispatcher(
        channels=channels,
        history=HistoryStore(),
        dead_letters=dead_letters,
        retry_policy=_fast_retry_policy(2),
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    outcome = await dispatcher.dispatch(message)

    assert outcome.status == DeliveryStatus.FAILED
    assert message.status == DeliveryStatus.FAILED
    entries = dead_letters.all()
    assert len(entries) == 1
    assert entries[0].attempts == 3  # max_attempts=2 retries -> 3 total attempts


async def test_dispatcher_does_not_retry_a_cancelled_result() -> None:
    channels = ChannelRegistry()
    cancelled = build_delivery_result(
        status=DeliveryStatus.CANCELLED, channel=NotificationChannel.EMAIL
    )
    stub = _ScriptedChannel(NotificationChannel.EMAIL, [cancelled])
    channels.register(stub)
    dispatcher = NotificationDispatcher(
        channels=channels,
        history=HistoryStore(),
        dead_letters=DeadLetterStore(),
        retry_policy=_fast_retry_policy(5),
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    outcome = await dispatcher.dispatch(message)

    assert outcome.status == DeliveryStatus.CANCELLED
    assert stub.calls == 1


async def test_dispatcher_rejects_when_rate_limited() -> None:
    class _AlwaysBlockingLimiter:
        async def check(self, *, user_id, organization_id, channel):
            return RateLimitStatus(allowed=False, remaining=0, limit=1, window_seconds=60)

    channels = ChannelRegistry()
    stub = _ScriptedChannel(
        NotificationChannel.EMAIL,
        [build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)],
    )
    channels.register(stub)
    dispatcher = NotificationDispatcher(
        channels=channels,
        history=HistoryStore(),
        dead_letters=DeadLetterStore(),
        rate_limiter=_AlwaysBlockingLimiter(),  # type: ignore[arg-type]
    )
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.INFORMATION, body="hi"
    )

    outcome = await dispatcher.dispatch(message)

    assert outcome.status == DeliveryStatus.FAILED
    assert stub.calls == 0
