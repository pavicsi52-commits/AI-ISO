"""Tests for application.py, resources.py, and helpers.py."""

from __future__ import annotations

import psutil
import pytest
from shared_core.monitoring import application, resources
from shared_core.monitoring.application import (
    ApplicationStatistics,
    capture_application_snapshot,
    measure_event_loop_delay,
)
from shared_core.monitoring.helpers import bytes_to_human_readable
from shared_core.monitoring.resources import capture_resource_snapshot

# --- application.py ---


def test_capture_application_snapshot_tolerates_open_files_being_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_psutil_error() -> list[object]:
        raise psutil.Error

    monkeypatch.setattr(application._process, "open_files", _raise_psutil_error)

    snapshot = capture_application_snapshot()

    assert snapshot.open_file_count == 0


def test_capture_application_snapshot_returns_plausible_values() -> None:
    snapshot = capture_application_snapshot()

    assert snapshot.cpu_percent >= 0.0
    assert snapshot.memory_rss_bytes > 0
    assert snapshot.memory_percent > 0.0
    assert snapshot.thread_count >= 1
    assert snapshot.open_file_count >= 0
    assert len(snapshot.garbage_collection.collections) == 3


async def test_measure_event_loop_delay_is_never_negative() -> None:
    delay = await measure_event_loop_delay(sample_seconds=0.01)

    assert delay >= 0.0


def test_application_statistics_records_requests_errors_exceptions_and_warnings() -> None:
    stats = ApplicationStatistics()

    stats.record_request(10.0)
    stats.record_request(20.0)
    stats.record_error()
    stats.record_exception()
    stats.record_warning()

    assert stats.request_count == 2
    assert stats.error_count == 1
    assert stats.exception_count == 1
    assert stats.warning_count == 1
    assert stats.average_response_time_ms == pytest.approx(15.0)


def test_application_statistics_average_response_time_is_zero_with_no_requests() -> None:
    assert ApplicationStatistics().average_response_time_ms == 0.0


def test_application_statistics_error_rate_is_zero_with_no_requests() -> None:
    assert ApplicationStatistics().error_rate == 0.0


def test_application_statistics_error_rate_is_a_fraction_of_requests() -> None:
    stats = ApplicationStatistics()
    stats.record_request(1.0)
    stats.record_request(1.0)
    stats.record_request(1.0)
    stats.record_request(1.0)
    stats.record_error()

    assert stats.error_rate == pytest.approx(0.25)


def test_application_statistics_reset_zeroes_every_counter() -> None:
    stats = ApplicationStatistics()
    stats.record_request(5.0)
    stats.record_error()
    stats.record_exception()
    stats.record_warning()

    stats.reset()

    assert stats.request_count == 0
    assert stats.error_count == 0
    assert stats.exception_count == 0
    assert stats.warning_count == 0
    assert stats.average_response_time_ms == 0.0


# --- resources.py ---


def test_disk_usage_reports_zeros_for_an_unreadable_mount_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_os_error(mount_point: str) -> object:
        raise OSError

    monkeypatch.setattr(psutil, "disk_usage", _raise_os_error)

    usage = resources._disk_usage("/unreadable")

    assert usage == resources.DiskUsage(
        mount_point="/unreadable", total_bytes=0, used_bytes=0, free_bytes=0, percent=0.0
    )


def test_capture_resource_snapshot_returns_plausible_host_values() -> None:
    snapshot = capture_resource_snapshot()

    assert snapshot.cpu_percent >= 0.0
    assert snapshot.cpu_count >= 1
    assert snapshot.memory_total_bytes > 0
    assert snapshot.memory_used_bytes > 0
    assert 0.0 <= snapshot.memory_percent <= 100.0
    assert snapshot.process_count >= 1


def test_capture_resource_snapshot_reports_at_least_one_disk() -> None:
    snapshot = capture_resource_snapshot()

    assert len(snapshot.disks) >= 1
    for disk in snapshot.disks:
        assert disk.total_bytes >= 0
        assert 0.0 <= disk.percent <= 100.0


def test_capture_resource_snapshot_network_counters_are_non_negative() -> None:
    network = capture_resource_snapshot().network

    assert network.bytes_sent >= 0
    assert network.bytes_received >= 0
    assert network.packets_sent >= 0
    assert network.packets_received >= 0


# --- helpers.py ---


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
    ],
)
def test_bytes_to_human_readable_formats_common_sizes(num_bytes: int, expected: str) -> None:
    assert bytes_to_human_readable(num_bytes) == expected


def test_bytes_to_human_readable_handles_petabyte_scale() -> None:
    result = bytes_to_human_readable(1024**5)

    assert result == "1.0 PB"


def test_bytes_to_human_readable_falls_back_to_exabytes_beyond_petabytes() -> None:
    result = bytes_to_human_readable(1024**6)

    assert result == "1.0 EB"
