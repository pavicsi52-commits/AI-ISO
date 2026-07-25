"""Tests for manager.py and factory.py."""

from __future__ import annotations

from shared_core.config.settings import EmailSettings
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.channels import ChannelRegistry, NotificationMessage
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.factory import create_notification_framework
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.manager import NotificationManager
from shared_core.notifications.preferences import NotificationPreferences, PreferencesStore
from shared_core.notifications.retry import DeadLetterStore
from shared_core.notifications.router import NotificationRouter


class _StubChannel:
    def __init__(self, channel_type: NotificationChannel):
        self.channel_type = channel_type
        self.sent: list[NotificationMessage] = []

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        self.sent.append(message)
        return build_delivery_result(status=DeliveryStatus.SENT, channel=self.channel_type)


def _manager() -> tuple[NotificationManager, _StubChannel, PreferencesStore]:
    preferences = PreferencesStore()
    channels = ChannelRegistry()
    stub = _StubChannel(NotificationChannel.EMAIL)
    channels.register(stub)
    history = HistoryStore()
    dead_letters = DeadLetterStore()
    manager = NotificationManager(
        channels=channels,
        dispatcher=NotificationDispatcher(
            channels=channels, history=history, dead_letters=dead_letters
        ),
        router=NotificationRouter(preferences),
        preferences=preferences,
        history=history,
        dead_letters=dead_letters,
    )
    return manager, stub, preferences


# --- manager.py ---


async def test_manager_send_delivers_over_the_users_preferred_channel() -> None:
    manager, stub, _preferences = _manager()

    result = await manager.send(
        user_id="user-1", notification_type=NotificationType.INFORMATION, body="hi"
    )

    assert result.status == DeliveryStatus.SENT
    assert len(stub.sent) == 1


async def test_manager_send_respects_an_explicit_channel_request() -> None:
    manager, stub, _preferences = _manager()

    result = await manager.send(
        user_id="user-1",
        notification_type=NotificationType.INFORMATION,
        body="hi",
        channel=NotificationChannel.EMAIL,
    )

    assert result.status == DeliveryStatus.SENT
    assert stub.sent[0].channel == NotificationChannel.EMAIL


async def test_manager_send_is_cancelled_when_the_channel_is_unsubscribed() -> None:
    manager, stub, preferences = _manager()
    preferences.unsubscribe("user-1", NotificationChannel.EMAIL)

    result = await manager.send(
        user_id="user-1",
        notification_type=NotificationType.INFORMATION,
        body="hi",
        channel=NotificationChannel.EMAIL,
    )

    assert result.status == DeliveryStatus.CANCELLED
    assert stub.sent == []


async def test_manager_send_records_to_history() -> None:
    manager, _stub, _preferences = _manager()

    await manager.send(user_id="user-1", notification_type=NotificationType.INFORMATION, body="hi")

    assert manager.analytics.sent_count() == 1


async def test_manager_broadcast_sends_to_every_subscriber() -> None:
    manager, stub, _preferences = _manager()
    manager.subscriptions.subscribe("user-1", "announcements")
    manager.subscriptions.subscribe("user-2", "announcements")

    results = await manager.broadcast(
        topic="announcements", notification_type=NotificationType.INFORMATION, body="hello everyone"
    )

    assert len(results) == 2
    assert all(result.status == DeliveryStatus.SENT for result in results)
    assert len(stub.sent) == 2


async def test_manager_broadcast_is_empty_for_a_topic_with_no_subscribers() -> None:
    manager, _stub, _preferences = _manager()

    results = await manager.broadcast(
        topic="empty-topic", notification_type=NotificationType.INFORMATION, body="hi"
    )

    assert results == []


async def test_manager_analytics_reflects_dispatcher_activity() -> None:
    manager, _stub, _preferences = _manager()

    await manager.send(user_id="user-1", notification_type=NotificationType.INFORMATION, body="a")
    await manager.send(user_id="user-1", notification_type=NotificationType.INFORMATION, body="b")

    assert manager.analytics.channel_usage() == {NotificationChannel.EMAIL: 2}


# --- factory.py ---


def test_create_notification_framework_with_no_email_settings_registers_no_channels() -> None:
    manager = create_notification_framework()

    assert manager.channels.registered_channels() == []


def test_create_notification_framework_registers_email_when_enabled() -> None:
    settings = EmailSettings(email_enabled=True, smtp_host="localhost", smtp_port=1025)

    manager = create_notification_framework(email_settings=settings)

    assert manager.channels.is_registered(NotificationChannel.EMAIL)


def test_create_notification_framework_skips_email_when_disabled() -> None:
    settings = EmailSettings(email_enabled=False)

    manager = create_notification_framework(email_settings=settings)

    assert not manager.channels.is_registered(NotificationChannel.EMAIL)


def test_create_notification_framework_wires_a_working_dispatcher_and_router() -> None:
    manager = create_notification_framework()

    assert isinstance(manager.dispatcher, NotificationDispatcher)
    assert isinstance(manager.router, NotificationRouter)
    assert manager.preferences.get("user-1") == NotificationPreferences(user_id="user-1")


def test_create_notification_framework_shares_history_between_manager_and_dispatcher() -> None:
    # Regression test: the manager's own `history`/`dead_letters` must be
    # the *same* instances the dispatcher writes to, not separate
    # freshly defaulted stores -- otherwise `manager.analytics` always
    # reads back empty even after real dispatches.
    settings = EmailSettings(email_enabled=True, smtp_host="localhost", smtp_port=1025)
    manager = create_notification_framework(email_settings=settings)

    assert manager.history is manager.dispatcher._history
    assert manager.dead_letters is manager.dispatcher._dead_letters
