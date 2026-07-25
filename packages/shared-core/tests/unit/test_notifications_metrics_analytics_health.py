"""Tests for metrics.py, analytics.py, and health.py."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.analytics import NotificationAnalytics
from shared_core.notifications.delivery import DeliveryStatus, build_delivery_result
from shared_core.notifications.health import (
    calculate_notification_health,
    check_http_provider_health,
    check_smtp_health,
    check_webhook_health,
)
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.metrics import (
    notification_delivery_latency_seconds,
    notifications_delivered_total,
    notifications_failed_total,
    notifications_sent_total,
    record_clicked,
    record_delivered,
    record_failed,
    record_latency,
    record_opened,
    record_retried,
    record_sent,
)
from shared_core.notifications.tracking import TrackingRecorder

# --- metrics.py ---


def test_record_sent_increments_the_counter() -> None:
    before = notifications_sent_total.labels(channel="email")._value.get()

    record_sent(NotificationChannel.EMAIL)

    assert notifications_sent_total.labels(channel="email")._value.get() == before + 1


def test_record_delivered_increments_the_counter() -> None:
    before = notifications_delivered_total.labels(channel="slack")._value.get()

    record_delivered(NotificationChannel.SLACK)

    assert notifications_delivered_total.labels(channel="slack")._value.get() == before + 1


def test_record_failed_increments_the_counter() -> None:
    before = notifications_failed_total.labels(channel="sms")._value.get()

    record_failed(NotificationChannel.SMS)

    assert notifications_failed_total.labels(channel="sms")._value.get() == before + 1


def test_record_opened_clicked_retried_do_not_raise() -> None:
    record_opened(NotificationChannel.EMAIL)
    record_clicked(NotificationChannel.EMAIL)
    record_retried(NotificationChannel.EMAIL)


def test_record_latency_observes_seconds_not_milliseconds() -> None:
    before = notification_delivery_latency_seconds.labels(channel="webhook")._sum.get()

    record_latency(NotificationChannel.WEBHOOK, 250.0)

    after = notification_delivery_latency_seconds.labels(channel="webhook")._sum.get()
    assert after == pytest.approx(before + 0.25)


# --- analytics.py ---


def test_analytics_sent_count_counts_sent_and_delivered() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.DELIVERED, channel=NotificationChannel.EMAIL
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.sent_count() == 2


def test_analytics_delivered_count_counts_only_delivered() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.DELIVERED, channel=NotificationChannel.EMAIL
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.delivered_count() == 1


def test_analytics_failed_count() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.failed_count() == 1


def test_analytics_bounced_count_detects_bounce_in_error_text() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.FAILED,
            channel=NotificationChannel.EMAIL,
            error="Mailbox bounce: 550",
        ),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL, error="timeout"
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.bounced_count() == 1


def test_analytics_retried_count_counts_attempts_beyond_the_first() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.FAILED, channel=NotificationChannel.EMAIL
        ),
    )
    history.record(
        "n1",
        attempt=2,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.retried_count() == 1


def test_analytics_opened_and_clicked_counts() -> None:
    tracking = TrackingRecorder()
    tracking.record_open("n1")
    tracking.record_click("n1", target_url="https://example.com")
    analytics = NotificationAnalytics(history=HistoryStore(), tracking=tracking)

    assert analytics.opened_count() == 1
    assert analytics.clicked_count() == 1


def test_analytics_average_latency_ms_is_zero_with_no_data() -> None:
    analytics = NotificationAnalytics(history=HistoryStore(), tracking=TrackingRecorder())

    assert analytics.average_latency_ms() == 0.0


def test_analytics_average_latency_ms_computes_the_mean() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL, latency_ms=100.0
        ),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL, latency_ms=200.0
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.average_latency_ms() == pytest.approx(150.0)


def test_analytics_average_latency_ms_filters_by_channel() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL, latency_ms=100.0
        ),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(
            status=DeliveryStatus.SENT, channel=NotificationChannel.SLACK, latency_ms=500.0
        ),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    assert analytics.average_latency_ms(channel=NotificationChannel.EMAIL) == pytest.approx(100.0)


def test_analytics_channel_usage_counts_per_channel() -> None:
    history = HistoryStore()
    history.record(
        "n1",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    history.record(
        "n2",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.EMAIL),
    )
    history.record(
        "n3",
        attempt=1,
        result=build_delivery_result(status=DeliveryStatus.SENT, channel=NotificationChannel.SLACK),
    )
    analytics = NotificationAnalytics(history=history, tracking=TrackingRecorder())

    usage = analytics.channel_usage()

    assert usage[NotificationChannel.EMAIL] == 2
    assert usage[NotificationChannel.SLACK] == 1


# --- health.py ---


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def http_server() -> Iterator[str]:
    server = HTTPServer(("localhost", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


async def test_check_smtp_health_succeeds_against_a_real_open_port() -> None:
    status = await check_smtp_health("localhost", 5672)  # RabbitMQ, a real always-open local port

    assert status == HealthStatus.HEALTHY


async def test_check_smtp_health_fails_for_a_closed_port() -> None:
    status = await check_smtp_health("localhost", 1)

    assert status == HealthStatus.UNHEALTHY


async def test_check_webhook_health_succeeds_against_a_real_server(http_server: str) -> None:
    status = await check_webhook_health(http_server)

    assert status == HealthStatus.HEALTHY


async def test_check_http_provider_health_succeeds_against_a_real_server(http_server: str) -> None:
    status = await check_http_provider_health(http_server)

    assert status == HealthStatus.HEALTHY


def test_calculate_notification_health_is_healthy_when_everything_is_healthy() -> None:
    report = calculate_notification_health(
        channel_statuses={
            NotificationChannel.EMAIL: HealthStatus.HEALTHY,
            NotificationChannel.SLACK: HealthStatus.HEALTHY,
        }
    )

    assert report.status == HealthStatus.HEALTHY


def test_calculate_notification_health_reflects_the_worst_channel() -> None:
    report = calculate_notification_health(
        channel_statuses={
            NotificationChannel.EMAIL: HealthStatus.HEALTHY,
            NotificationChannel.SLACK: HealthStatus.UNHEALTHY,
        }
    )

    assert report.status == HealthStatus.UNHEALTHY


def test_calculate_notification_health_reflects_queue_status() -> None:
    report = calculate_notification_health(
        channel_statuses={NotificationChannel.EMAIL: HealthStatus.HEALTHY},
        queue_status=HealthStatus.UNHEALTHY,
    )

    assert report.status == HealthStatus.UNHEALTHY
