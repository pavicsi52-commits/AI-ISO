"""Tests for log output handlers, rotation, and retention."""

from __future__ import annotations

import gzip
import logging
import os
import time
from pathlib import Path

import pytest
from shared_core.logging.exceptions import LogHandlerError
from shared_core.logging.handlers import (
    build_console_handler,
    build_file_handler,
    build_otel_handler,
)
from shared_core.logging.json_formatter import JsonFormatter
from shared_core.logging.retention import cleanup_old_logs
from shared_core.logging.rotation import SizeAndTimeRotatingHandler


def _make_record(msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


# --- handlers ---


def test_build_console_handler_writes_json_to_stdout() -> None:
    handler = build_console_handler(service="svc", environment="testing")

    assert isinstance(handler, logging.StreamHandler)
    assert isinstance(handler.formatter, JsonFormatter)


def test_build_file_handler_creates_parent_directories(tmp_path: Path) -> None:
    log_file = tmp_path / "nested" / "app.log"

    handler = build_file_handler(service="svc", environment="testing", file_path=str(log_file))
    handler.emit(_make_record("hello"))
    handler.close()

    assert log_file.exists()
    assert "hello" in log_file.read_text(encoding="utf-8")


def test_build_file_handler_raises_log_handler_error_on_unwritable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_mkdir(*args: object, **kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _fail_mkdir)

    with pytest.raises(LogHandlerError):
        build_file_handler(
            service="svc", environment="testing", file_path=str(tmp_path / "x" / "app.log")
        )


def test_build_otel_handler_returns_a_logging_handler() -> None:
    handler = build_otel_handler(service_name="svc")

    handler.emit(_make_record("otel test"))  # should not raise


# --- rotation ---


def test_rotating_handler_rolls_over_on_max_bytes(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    handler = SizeAndTimeRotatingHandler(
        str(log_file), max_bytes=200, backup_count=5, compress=False
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    for i in range(50):
        handler.emit(_make_record(f"line {i} " + "x" * 20))
    handler.close()

    rotated = list(tmp_path.glob("app.log.*"))
    assert rotated, "expected at least one rotated file"


def test_rotating_handler_compresses_rotated_files(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    handler = SizeAndTimeRotatingHandler(
        str(log_file), max_bytes=100, backup_count=5, compress=True
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    for i in range(50):
        handler.emit(_make_record(f"line {i} " + "x" * 20))
    handler.close()

    rotated = list(tmp_path.glob("*.gz"))
    assert rotated, "expected at least one compressed rotated file"
    with gzip.open(rotated[0], "rt", encoding="utf-8") as f:
        assert "line" in f.read()


def test_rotating_handler_does_not_rotate_below_max_bytes(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    handler = SizeAndTimeRotatingHandler(
        str(log_file), max_bytes=1_000_000, backup_count=5, compress=False
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    handler.emit(_make_record("small message"))
    handler.close()

    assert list(tmp_path.glob("app.log.*")) == []


# --- retention ---


def test_cleanup_old_logs_removes_files_past_retention(tmp_path: Path) -> None:
    old_file = tmp_path / "app.log.2020-01-01"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - (100 * 86_400)
    os.utime(old_file, (old_time, old_time))

    removed = cleanup_old_logs(tmp_path, retention_days=90)

    assert old_file in removed
    assert not old_file.exists()


def test_cleanup_old_logs_keeps_recent_files(tmp_path: Path) -> None:
    recent_file = tmp_path / "app.log.today"
    recent_file.write_text("recent", encoding="utf-8")

    removed = cleanup_old_logs(tmp_path, retention_days=90)

    assert removed == []
    assert recent_file.exists()


def test_cleanup_old_logs_handles_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert cleanup_old_logs(missing, retention_days=90) == []
