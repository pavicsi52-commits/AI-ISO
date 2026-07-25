"""Tests for alerts.py and metrics.py."""

from __future__ import annotations

from shared_core.monitoring.alerts import Alert, AlertCategory, AlertDispatcher
from shared_core.monitoring.metrics import (
    ai_request_duration_seconds,
    automation_duration_seconds,
    connector_count,
    database_connections_in_use,
    plugin_count,
    storage_usage_bytes,
    validation_duration_seconds,
    workflow_duration_seconds,
)
from shared_core.monitoring.thresholds import ThresholdLevel

# --- alerts.py ---


async def test_alert_dispatcher_fans_out_to_every_registered_sink() -> None:
    received: list[Alert] = []

    async def sink_a(alert: Alert) -> None:
        received.append(alert)

    async def sink_b(alert: Alert) -> None:
        received.append(alert)

    dispatcher = AlertDispatcher()
    dispatcher.register_sink(sink_a)
    dispatcher.register_sink(sink_b)
    alert = Alert(category=AlertCategory.HIGH_CPU, level=ThresholdLevel.CRITICAL, message="cpu hot")

    await dispatcher.trigger(alert)

    assert received == [alert, alert]


async def test_alert_dispatcher_trigger_never_raises_with_no_sinks_registered() -> None:
    dispatcher = AlertDispatcher()
    alert = Alert(category=AlertCategory.DISK_FULL, level=ThresholdLevel.HIGH, message="disk full")

    await dispatcher.trigger(alert)


def test_alert_carries_its_configured_fields() -> None:
    alert = Alert(
        category=AlertCategory.DATABASE_DOWN,
        level=ThresholdLevel.CRITICAL,
        message="postgres unreachable",
        metric_name="db_up",
        value=0.0,
    )

    assert alert.category == AlertCategory.DATABASE_DOWN
    assert alert.level == ThresholdLevel.CRITICAL
    assert alert.metric_name == "db_up"
    assert alert.value == 0.0
    assert alert.triggered_at is not None


def test_alert_category_covers_every_docs_023_category() -> None:
    expected = {
        "health_failure",
        "dependency_failure",
        "high_cpu",
        "high_memory",
        "disk_full",
        "database_down",
        "redis_down",
        "queue_overflow",
        "storage_failure",
        "plugin_failure",
        "connector_failure",
        "worker_failure",
        "high_error_rate",
        "high_latency",
    }

    assert {category.value for category in AlertCategory} == expected


# --- metrics.py ---


def test_database_connections_in_use_is_settable_per_service() -> None:
    database_connections_in_use.labels(service="gateway").set(5)

    assert database_connections_in_use.labels(service="gateway")._value.get() == 5.0


def test_storage_usage_bytes_is_settable_per_bucket() -> None:
    storage_usage_bytes.labels(bucket="artifacts").set(1024.0)

    assert storage_usage_bytes.labels(bucket="artifacts")._value.get() == 1024.0


def test_workflow_duration_seconds_records_an_observation() -> None:
    before = workflow_duration_seconds.labels(workflow="deploy")._sum.get()

    workflow_duration_seconds.labels(workflow="deploy").observe(1.5)

    assert workflow_duration_seconds.labels(workflow="deploy")._sum.get() >= before + 1.5


def test_automation_duration_seconds_records_an_observation() -> None:
    before = automation_duration_seconds.labels(automation="cleanup")._sum.get()

    automation_duration_seconds.labels(automation="cleanup").observe(0.5)

    assert automation_duration_seconds.labels(automation="cleanup")._sum.get() >= before + 0.5


def test_validation_duration_seconds_records_an_observation() -> None:
    before = validation_duration_seconds.labels(layer="schema")._sum.get()

    validation_duration_seconds.labels(layer="schema").observe(0.1)

    assert validation_duration_seconds.labels(layer="schema")._sum.get() >= before + 0.1


def test_ai_request_duration_seconds_records_an_observation() -> None:
    before = ai_request_duration_seconds.labels(provider="anthropic")._sum.get()

    ai_request_duration_seconds.labels(provider="anthropic").observe(2.0)

    assert ai_request_duration_seconds.labels(provider="anthropic")._sum.get() >= before + 2.0


def test_plugin_count_is_settable_per_service() -> None:
    plugin_count.labels(service="gateway").set(3)

    assert plugin_count.labels(service="gateway")._value.get() == 3.0


def test_connector_count_is_settable_per_service() -> None:
    connector_count.labels(service="gateway").set(7)

    assert connector_count.labels(service="gateway")._value.get() == 7.0
