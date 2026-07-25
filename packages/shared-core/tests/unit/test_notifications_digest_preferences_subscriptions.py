"""Tests for digest.py, preferences.py, and subscriptions.py."""

from __future__ import annotations

from datetime import time

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.channels import NotificationMessage, build_notification
from shared_core.notifications.digest import DigestFrequency, build_digest
from shared_core.notifications.exceptions import InvalidPreferenceError, SubscriptionError
from shared_core.notifications.preferences import NotificationPreferences, PreferencesStore
from shared_core.notifications.subscriptions import SubscriptionRegistry

# --- digest.py ---


def _msg(
    body: str,
    subject: str = "s",
    notification_type: NotificationType = NotificationType.INFORMATION,
) -> NotificationMessage:
    return build_notification(
        channel=NotificationChannel.EMAIL,
        notification_type=notification_type,
        body=body,
        subject=subject,
    )


def test_build_digest_groups_by_notification_type() -> None:
    messages = [
        _msg("a", notification_type=NotificationType.INFORMATION),
        _msg("b", notification_type=NotificationType.WARNING),
        _msg("c", notification_type=NotificationType.INFORMATION),
    ]

    digest = build_digest("user-1", messages)

    by_type = {group.notification_type: len(group.messages) for group in digest.groups}
    assert by_type == {"information": 2, "warning": 1}
    assert digest.total_count == 3


def test_build_digest_removes_duplicates() -> None:
    messages = [_msg("same body", subject="same"), _msg("same body", subject="same")]

    digest = build_digest("user-1", messages)

    assert digest.total_count == 1


def test_build_digest_respects_max_items() -> None:
    messages = [_msg(f"body-{i}") for i in range(10)]

    digest = build_digest("user-1", messages, max_items=3)

    assert digest.total_count == 3


def test_digest_frequency_covers_every_documented_value() -> None:
    expected = {"none", "hourly", "daily", "weekly", "monthly"}
    assert {frequency.value for frequency in DigestFrequency} == expected


# --- preferences.py ---


def test_notification_preferences_defaults_are_permissive() -> None:
    preferences = NotificationPreferences(user_id="user-1")

    assert preferences.allows(
        channel=NotificationChannel.EMAIL, category=NotificationType.INFORMATION
    )


def test_notification_preferences_allows_is_false_when_muted() -> None:
    preferences = NotificationPreferences(user_id="user-1", muted=True)

    assert not preferences.allows(
        channel=NotificationChannel.EMAIL, category=NotificationType.INFORMATION
    )


def test_notification_preferences_allows_is_false_for_an_unsubscribed_channel() -> None:
    preferences = NotificationPreferences(
        user_id="user-1", unsubscribed_channels={NotificationChannel.SMS}
    )

    assert not preferences.allows(
        channel=NotificationChannel.SMS, category=NotificationType.INFORMATION
    )
    assert preferences.allows(
        channel=NotificationChannel.EMAIL, category=NotificationType.INFORMATION
    )


def test_notification_preferences_allows_is_false_for_a_muted_category() -> None:
    preferences = NotificationPreferences(
        user_id="user-1", muted_categories={NotificationType.MAINTENANCE}
    )

    assert not preferences.allows(
        channel=NotificationChannel.EMAIL, category=NotificationType.MAINTENANCE
    )


def test_quiet_hours_within_a_same_day_window() -> None:
    preferences = NotificationPreferences(
        user_id="user-1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
    )

    assert preferences.is_within_quiet_hours(time(12, 0)) is True
    assert preferences.is_within_quiet_hours(time(20, 0)) is False


def test_quiet_hours_wrapping_past_midnight() -> None:
    preferences = NotificationPreferences(
        user_id="user-1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
    )

    assert preferences.is_within_quiet_hours(time(23, 0)) is True
    assert preferences.is_within_quiet_hours(time(3, 0)) is True
    assert preferences.is_within_quiet_hours(time(12, 0)) is False


def test_quiet_hours_is_false_when_unconfigured() -> None:
    preferences = NotificationPreferences(user_id="user-1")

    assert preferences.is_within_quiet_hours(time(3, 0)) is False


def test_preferences_store_get_creates_a_permissive_default() -> None:
    store = PreferencesStore()

    preferences = store.get("user-1")

    assert preferences.user_id == "user-1"
    assert preferences.muted is False


def test_preferences_store_set_replaces_stored_preferences() -> None:
    store = PreferencesStore()
    custom = NotificationPreferences(user_id="user-1", language="fr")

    store.set(custom)

    assert store.get("user-1").language == "fr"


def test_preferences_store_mute_and_unmute() -> None:
    store = PreferencesStore()

    store.mute("user-1")
    assert store.get("user-1").muted is True

    store.unmute("user-1")
    assert store.get("user-1").muted is False


def test_preferences_store_unsubscribe() -> None:
    store = PreferencesStore()

    store.unsubscribe("user-1", NotificationChannel.SMS)

    assert NotificationChannel.SMS in store.get("user-1").unsubscribed_channels


def test_preferences_store_set_channel_priority() -> None:
    store = PreferencesStore()

    store.set_channel_priority("user-1", [NotificationChannel.SLACK, NotificationChannel.EMAIL])

    assert store.get("user-1").channel_priority == [
        NotificationChannel.SLACK,
        NotificationChannel.EMAIL,
    ]


def test_preferences_store_set_channel_priority_rejects_duplicates() -> None:
    store = PreferencesStore()

    with pytest.raises(InvalidPreferenceError):
        store.set_channel_priority("user-1", [NotificationChannel.EMAIL, NotificationChannel.EMAIL])


# --- subscriptions.py ---


def test_subscription_registry_subscribe_and_is_subscribed() -> None:
    registry = SubscriptionRegistry()

    registry.subscribe("user-1", "billing-alerts")

    assert registry.is_subscribed("user-1", "billing-alerts") is True
    assert registry.is_subscribed("user-2", "billing-alerts") is False


def test_subscription_registry_unsubscribe() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("user-1", "billing-alerts")

    registry.unsubscribe("user-1", "billing-alerts")

    assert registry.is_subscribed("user-1", "billing-alerts") is False


def test_subscription_registry_unsubscribe_raises_when_not_subscribed() -> None:
    with pytest.raises(SubscriptionError):
        SubscriptionRegistry().unsubscribe("user-1", "billing-alerts")


def test_subscription_registry_subscribers_of_a_broadcast_group() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("user-1", "org-42-announcements")
    registry.subscribe("user-2", "org-42-announcements")

    subscribers = registry.subscribers_of("org-42-announcements")

    assert subscribers == ["user-1", "user-2"]


def test_subscription_registry_topics_of_a_user() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("user-1", "topic-a")
    registry.subscribe("user-1", "topic-b")

    assert registry.topics_of("user-1") == ["topic-a", "topic-b"]
