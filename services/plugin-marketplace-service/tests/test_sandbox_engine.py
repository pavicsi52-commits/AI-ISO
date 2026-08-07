"""Tests for ``app.sandbox.engine``: ``PluginExecutionSandbox``/
``PluginExecutionPolicy``/``SandboxViolationError``/``SandboxExecutionError``/
``SandboxExecutionResult``.

``run_entry_point`` spawns a real ``python`` subprocess and enforces a
real ``asyncio.wait_for``-based timeout -- ``asyncio.create_subprocess_exec``
is never mocked, so the timeout test genuinely spawns and kills a
process.
"""

from __future__ import annotations

import pytest

from app.models.enums import PluginPermissionCategory
from app.sandbox.engine import (
    PluginExecutionPolicy,
    PluginExecutionSandbox,
    SandboxExecutionError,
    SandboxViolationError,
)

_PYTHON = "python"
"""Resolved off PATH -- ``uv run`` puts this test's own venv ``Scripts``
directory on PATH, so this is the same real interpreter running the
test, reached the same way a plugin's own entry point would be."""


def _sandbox(**policy_overrides: object) -> PluginExecutionSandbox:
    policy = PluginExecutionPolicy(**policy_overrides)
    return PluginExecutionSandbox("installation-1", policy)


# ---- check_granted ----------------------------------------------------------------


def test_check_granted_passes_for_a_granted_category() -> None:
    sandbox = _sandbox(granted_categories=frozenset({PluginPermissionCategory.INVENTORY}))
    sandbox.check_granted(PluginPermissionCategory.INVENTORY)  # does not raise


def test_check_granted_raises_for_an_ungranted_category() -> None:
    sandbox = _sandbox(granted_categories=frozenset({PluginPermissionCategory.INVENTORY}))
    with pytest.raises(SandboxViolationError, match="network"):
        sandbox.check_granted(PluginPermissionCategory.NETWORK)


def test_check_granted_raises_when_nothing_is_granted() -> None:
    sandbox = _sandbox()
    with pytest.raises(SandboxViolationError):
        sandbox.check_granted(PluginPermissionCategory.CUSTOM)


# ---- check_filesystem_access -------------------------------------------------------


def test_check_filesystem_access_passes_for_a_matching_glob() -> None:
    sandbox = _sandbox(
        granted_categories=frozenset({PluginPermissionCategory.FILESYSTEM}),
        allowed_filesystem_globs=("/data/*", "/tmp/plugin-*"),
    )
    sandbox.check_filesystem_access("/data/inventory.csv")  # does not raise
    sandbox.check_filesystem_access("/tmp/plugin-cache.json")  # does not raise


def test_check_filesystem_access_raises_when_filesystem_not_granted_at_all() -> None:
    sandbox = _sandbox(allowed_filesystem_globs=("/data/*",))
    with pytest.raises(SandboxViolationError, match="filesystem"):
        sandbox.check_filesystem_access("/data/inventory.csv")


def test_check_filesystem_access_raises_when_path_not_covered_by_any_glob() -> None:
    sandbox = _sandbox(
        granted_categories=frozenset({PluginPermissionCategory.FILESYSTEM}),
        allowed_filesystem_globs=("/data/*",),
    )
    with pytest.raises(SandboxViolationError, match="/etc/passwd"):
        sandbox.check_filesystem_access("/etc/passwd")


# ---- check_network_access ------------------------------------------------------------


def test_check_network_access_passes_for_an_allowed_host() -> None:
    sandbox = _sandbox(
        granted_categories=frozenset({PluginPermissionCategory.NETWORK}),
        allowed_network_hosts=("api.example.com", "hooks.example.com"),
    )
    sandbox.check_network_access("api.example.com")  # does not raise


def test_check_network_access_raises_when_network_not_granted_at_all() -> None:
    sandbox = _sandbox(allowed_network_hosts=("api.example.com",))
    with pytest.raises(SandboxViolationError, match="network"):
        sandbox.check_network_access("api.example.com")


def test_check_network_access_raises_for_a_disallowed_host() -> None:
    sandbox = _sandbox(
        granted_categories=frozenset({PluginPermissionCategory.NETWORK}),
        allowed_network_hosts=("api.example.com",),
    )
    with pytest.raises(SandboxViolationError, match=r"evil\.example\.com"):
        sandbox.check_network_access("evil.example.com")


# ---- check_memory_usage --------------------------------------------------------------


def test_check_memory_usage_returns_a_positive_float_within_a_generous_limit() -> None:
    sandbox = _sandbox(memory_limit_mb=100_000.0)
    usage = sandbox.check_memory_usage()
    assert isinstance(usage, float)
    assert usage > 0.0


def test_check_memory_usage_raises_when_over_an_unrealistically_low_limit() -> None:
    sandbox = _sandbox(memory_limit_mb=0.001)
    with pytest.raises(SandboxViolationError):
        sandbox.check_memory_usage()


# ---- run_entry_point: real subprocess execution ---------------------------------------


async def test_run_entry_point_executes_a_real_process_and_captures_stdout() -> None:
    sandbox = _sandbox(execution_timeout_seconds=10.0)
    result = await sandbox.run_entry_point([_PYTHON, "-c", "print('hello')"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False
    assert result.duration_seconds >= 0.0


async def test_run_entry_point_captures_a_nonzero_exit_code() -> None:
    sandbox = _sandbox(execution_timeout_seconds=10.0)
    result = await sandbox.run_entry_point([_PYTHON, "-c", "import sys; sys.exit(3)"])
    assert result.exit_code == 3
    assert result.timed_out is False


async def test_run_entry_point_captures_real_stderr() -> None:
    sandbox = _sandbox(execution_timeout_seconds=10.0)
    result = await sandbox.run_entry_point([_PYTHON, "-c", "import sys; sys.stderr.write('boom')"])
    assert "boom" in result.stderr


async def test_run_entry_point_real_timeout_kills_the_process() -> None:
    """A real spawn-then-kill: no mocking of ``asyncio.create_subprocess_exec``."""
    sandbox = _sandbox(execution_timeout_seconds=0.3)
    result = await sandbox.run_entry_point([_PYTHON, "-c", "import time; time.sleep(5)"])
    assert result.timed_out is True
    assert result.duration_seconds < 2.0


async def test_run_entry_point_raises_sandbox_execution_error_for_missing_binary() -> None:
    sandbox = _sandbox(execution_timeout_seconds=5.0)
    with pytest.raises(SandboxExecutionError):
        await sandbox.run_entry_point(["this-binary-does-not-exist-xyz"])
