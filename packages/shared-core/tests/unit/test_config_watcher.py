"""Tests for the development-only configuration hot-reload watcher."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from shared_core.config import Environment
from shared_core.config.cache import clear_settings_cache, get_settings
from shared_core.config.watcher import ConfigWatcher

_POLL_INTERVAL = 0.01


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


async def test_start_is_a_noop_outside_hot_reload_environments(tmp_path: Path) -> None:
    watcher = ConfigWatcher(Environment.PRODUCTION, files=[tmp_path / ".env"])

    watcher.start()

    assert watcher.is_running is False


async def test_start_runs_in_development(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIIOS_APP_NAME=base\n", encoding="utf-8")
    watcher = ConfigWatcher(
        Environment.DEVELOPMENT, files=[env_file], poll_interval_seconds=_POLL_INTERVAL
    )

    watcher.start()
    try:
        assert watcher.is_running is True
    finally:
        await watcher.stop()


async def test_reloads_settings_when_a_watched_file_changes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIIOS_APP_NAME=base\n", encoding="utf-8")
    watcher = ConfigWatcher(
        Environment.DEVELOPMENT, files=[env_file], poll_interval_seconds=_POLL_INTERVAL
    )
    first = get_settings()

    watcher.start()
    try:
        await asyncio.sleep(_POLL_INTERVAL * 2)
        # Ensure the mtime actually advances on filesystems with coarse
        # timestamp resolution.
        new_mtime = env_file.stat().st_mtime + 1
        env_file.write_text("AIIOS_APP_NAME=changed\n", encoding="utf-8")
        os.utime(env_file, (new_mtime, new_mtime))
        await asyncio.sleep(_POLL_INTERVAL * 5)

        assert get_settings() is not first
    finally:
        await watcher.stop()


async def test_on_reload_callback_is_invoked(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIIOS_APP_NAME=base\n", encoding="utf-8")
    calls: list[None] = []
    watcher = ConfigWatcher(
        Environment.DEVELOPMENT,
        files=[env_file],
        poll_interval_seconds=_POLL_INTERVAL,
        on_reload=lambda: calls.append(None),
    )

    watcher.start()
    try:
        await asyncio.sleep(_POLL_INTERVAL * 2)
        new_mtime = env_file.stat().st_mtime + 1
        env_file.write_text("AIIOS_APP_NAME=changed\n", encoding="utf-8")
        os.utime(env_file, (new_mtime, new_mtime))
        await asyncio.sleep(_POLL_INTERVAL * 5)

        assert calls
    finally:
        await watcher.stop()


async def test_start_is_idempotent_while_running(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AIIOS_APP_NAME=base\n", encoding="utf-8")
    watcher = ConfigWatcher(
        Environment.DEVELOPMENT, files=[env_file], poll_interval_seconds=_POLL_INTERVAL
    )

    watcher.start()
    try:
        task_before = watcher._task
        watcher.start()
        assert watcher._task is task_before
    finally:
        await watcher.stop()


async def test_stop_before_start_is_a_noop() -> None:
    watcher = ConfigWatcher(Environment.DEVELOPMENT, files=[])

    await watcher.stop()

    assert watcher.is_running is False


async def test_defaults_to_env_files_for_the_given_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    watcher = ConfigWatcher(Environment.DEVELOPMENT)

    assert watcher._files == [Path(".env")]
