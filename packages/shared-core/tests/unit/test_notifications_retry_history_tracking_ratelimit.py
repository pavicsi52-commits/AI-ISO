"""Tests for retry.py, history.py, tracking.py, and ratelimit.py."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from shared_core.cache.manager import CacheManager
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.channels import build_notification
from shared_core.notifications.delivery import DeliveryStatus, build_delivery_result
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.ratelimit import build_notification_rate_limiter
from shared_core.notifications.retry import (
    DeadLetterStore,
    classify_delivery_failure,
    notification_retry_policy,
)
from shared_core.notifications.tracking import (
    TrackingRecorder,
    build_click_tracking_url,
    build_open_tracking_url,
)


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def cache_manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


# --- retry.py ---


def test_notification_retry_policy_has_a_sensible_default_max_attempts() -> None:
    policy = notification_retry_policy()

    assert policy.max_attempts == 3


def test_classify_delivery_failure_retries_a_plain_failed_status() -> None:
    result = build_delivery_result(status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL)

    assert classify_delivery_failure(result) is True


def test_classify_delivery_failure_never_retries_cancelled_or_expired() -> None:
    cancelled = build_delivery_result(
        status=DeliveryStatus.CANCELLED, channel=NotificationChannel.EMAIL
    )
    expired = build_delivery_result(
        status=DeliveryStatus.EXPIRED, channel=NotificationChannel.EMAIL
    )

    assert classify_delivery_failure(cancelled) is False
    assert classify_delivery_failure(expired) is False


def test_classify_delivery_failure_does_not_retry_a_successful_result() -> None:
    result = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    assert classify_delivery_failure(result) is False


def test_dead_letter_store_add_and_all_roundtrips() -> None:
    store = DeadLetterStore()
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.ERROR, body="x"
    )
    result = build_delivery_result(status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL)

    store.add(message, last_result=result, attempts=3)

    entries = store.all()
    assert len(entries) == 1
    assert entries[0].attempts == 3


def test_dead_letter_store_pop_for_manual_retry_removes_the_entry() -> None:
    store = DeadLetterStore()
    message = build_notification(
        channel=NotificationChannel.EMAIL, notification_type=NotificationType.ERROR, body="x"
    )
    result = build_delivery_result(status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL)
    store.add(message, last_result=result, attempts=3)

    popped = store.pop_for_manual_retry(message.notification_id)

    assert popped is message
    assert store.all() == []


def test_dead_letter_store_pop_for_manual_retry_returns_none_when_not_found() -> None:
    assert DeadLetterStore().pop_for_manual_retry("nope") is None


# --- history.py ---


def test_history_store_record_and_for_notification_roundtrips() -> None:
    store = HistoryStore()
    result = build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL)

    store.record("notif-1", attempt=1, result=result)

    entries = store.for_notification("notif-1")
    assert len(entries) == 1
    assert entries[0].attempt == 1


def test_history_store_latest_status_returns_the_most_recent() -> None:
    store = HistoryStore()
    store.record(
        "notif-1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL
        ),
    )
    store.record(
        "notif-1",
        attempt=2,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )

    assert store.latest_status("notif-1") == DeliveryStatus.SENT


def test_history_store_latest_status_is_none_for_an_unknown_notification() -> None:
    assert HistoryStore().latest_status("nope") is None


def test_history_store_by_channel_filters_correctly() -> None:
    store = HistoryStore()
    store.record(
        "notif-1",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    store.record(
        "notif-2",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.SLACK),
    )

    email_entries = store.by_channel(NotificationChannel.EMAIL)

    assert len(email_entries) == 1
    assert email_entries[0].notification_id == "notif-1"


def test_history_store_respects_a_bounded_max_size() -> None:
    store = HistoryStore(max_size=2)
    for i in range(5):
        store.record(
            f"notif-{i}",
            attempt=1,
            result=build_delivery_result(
                status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL
            ),
        )

    assert len(store.entries()) == 2


# --- tracking.py ---


def test_build_open_tracking_url_embeds_the_notification_id() -> None:
    url = build_open_tracking_url("notif-1", base_url="https://api.aiios.local")

    assert url == "https://api.aiios.local/track/open/notif-1"


def test_build_click_tracking_url_embeds_the_target() -> None:
    url = build_click_tracking_url(
        "notif-1", "https://example.com/report", base_url="https://api.aiios.local"
    )

    assert url.startswith("https://api.aiios.local/track/click/notif-1?")
    assert "to=https%3A%2F%2Fexample.com%2Freport" in url


def test_tracking_recorder_records_opens_and_clicks() -> None:
    recorder = TrackingRecorder()

    recorder.record_open("notif-1")
    recorder.record_click("notif-1", target_url="https://example.com")

    events = recorder.events_for("notif-1")
    assert {event.kind for event in events} == {"open", "click"}
    assert len(recorder.all_events()) == 2


def test_tracking_recorder_events_for_filters_by_notification() -> None:
    recorder = TrackingRecorder()
    recorder.record_open("notif-1")
    recorder.record_open("notif-2")

    assert len(recorder.events_for("notif-1")) == 1


# --- ratelimit.py ---


async def test_notification_rate_limiter_allows_within_limits(cache_manager: CacheManager) -> None:
    limiter = build_notification_rate_limiter(
        cache_manager, max_per_user=5, max_per_organization=5, max_per_channel=5, max_global=5
    )

    status = await limiter.check(
        user_id="user-1", organization_id="org-1", channel=NotificationChannel.EMAIL
    )

    assert status.allowed is True


async def test_notification_rate_limiter_blocks_once_the_user_scope_is_exhausted(
    cache_manager: CacheManager,
) -> None:
    limiter = build_notification_rate_limiter(
        cache_manager,
        max_per_user=1,
        max_per_organization=100,
        max_per_channel=100,
        max_global=100,
    )

    first = await limiter.check(
        user_id="user-1", organization_id="org-1", channel=NotificationChannel.EMAIL
    )
    second = await limiter.check(
        user_id="user-1", organization_id="org-1", channel=NotificationChannel.EMAIL
    )

    assert first.allowed is True
    assert second.allowed is False


async def test_notification_rate_limiter_isolates_scopes_with_the_same_identifier_string(
    cache_manager: CacheManager,
) -> None:
    limiter = build_notification_rate_limiter(
        cache_manager,
        max_per_user=1,
        max_per_organization=1,
        max_per_channel=100,
        max_global=100,
    )

    # Same literal string used as both a user_id and an organization_id --
    # without scope-prefixed keys these would share one counter.
    shared_id = "shared-id"
    user_status = await limiter.check(
        user_id=shared_id, organization_id=None, channel=NotificationChannel.EMAIL
    )
    org_status = await limiter.check(
        user_id=None, organization_id=shared_id, channel=NotificationChannel.EMAIL
    )

    assert user_status.allowed is True
    assert org_status.allowed is True
