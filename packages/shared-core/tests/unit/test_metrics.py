"""Tests for the Prometheus metrics framework."""

from __future__ import annotations

from prometheus_client import generate_latest
from shared_core.metrics import (
    cache_hits_total,
    create_counter,
    create_gauge,
    create_histogram,
    default_registry,
    http_requests_total,
)


def test_create_counter_is_namespaced() -> None:
    counter = create_counter("widgets_processed_total", "Widgets processed.")

    counter.inc()

    exposed = generate_latest(default_registry).decode("utf-8")
    assert "aiios_widgets_processed_total" in exposed


def test_create_gauge_tracks_value() -> None:
    gauge = create_gauge("active_widgets", "Currently active widgets.")

    gauge.set(5)

    exposed = generate_latest(default_registry).decode("utf-8")
    assert "aiios_active_widgets 5.0" in exposed


def test_create_histogram_observes_values() -> None:
    histogram = create_histogram("widget_duration_seconds", "Widget processing duration.")

    histogram.observe(0.5)

    exposed = generate_latest(default_registry).decode("utf-8")
    assert "aiios_widget_duration_seconds_count" in exposed


def test_standard_http_metrics_are_registered() -> None:
    http_requests_total.labels(method="GET", path="/health", status_code="200").inc()

    exposed = generate_latest(default_registry).decode("utf-8")
    assert "aiios_http_requests_total" in exposed


def test_standard_cache_metrics_are_registered() -> None:
    cache_hits_total.labels(cache="test").inc()

    exposed = generate_latest(default_registry).decode("utf-8")
    assert "aiios_cache_hits_total" in exposed
