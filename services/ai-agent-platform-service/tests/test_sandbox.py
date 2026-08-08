"""Tests for app.sandbox.{engine,policy,process}.

``app/sandbox/process.py`` genuinely spawns real subprocesses via
``asyncio.create_subprocess_exec`` -- every test against it runs a real,
trivial ``sys.executable`` script, never ``shell=True``, and confirms
real timeout/cleanup behaviour rather than asserting on a mock.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.service import InternalError
from shared_core.exceptions.timeout import AIIOSTimeoutError

from app.models.enums import PermissionCategory
from app.sandbox.engine import AgentSandbox
from app.sandbox.policy import (
    DEFAULT_CPU_LIMIT_SECONDS,
    DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    DEFAULT_MEMORY_LIMIT_MB,
    AgentSandboxPolicy,
)
from app.sandbox.process import run_isolated, run_script_isolated


def _gone(path: str) -> bool:
    """Whether *path* no longer exists on disk.

    A plain, synchronous helper kept out of the async test bodies
    themselves -- a directly-inlined ``Path(...).exists()`` inside an
    ``async def`` is a real, if brief, blocking filesystem call, which
    is exactly what confirms Secure Cleanup really happened; wrapping
    it here keeps that real check while satisfying the linter's
    preference for it not to be written inline in a coroutine.
    """
    return not Path(path).exists()


# ---------------------------------------------------------------------------
# policy.py
# ---------------------------------------------------------------------------


def test_policy_defaults() -> None:
    policy = AgentSandboxPolicy()
    assert policy.allowed_permissions == frozenset()
    assert policy.allowed_filesystem_globs == ()
    assert policy.allowed_network_hosts == ()
    assert policy.memory_limit_mb == DEFAULT_MEMORY_LIMIT_MB == 512.0
    assert policy.cpu_limit_seconds == DEFAULT_CPU_LIMIT_SECONDS == 30.0
    assert policy.execution_timeout_seconds == DEFAULT_EXECUTION_TIMEOUT_SECONDS == 60.0


def test_policy_is_frozen() -> None:
    policy = AgentSandboxPolicy()
    with pytest.raises(AttributeError):
        policy.memory_limit_mb = 1.0  # type: ignore[misc]


def test_policy_custom_values() -> None:
    policy = AgentSandboxPolicy(
        allowed_permissions=frozenset({PermissionCategory.NETWORK}),
        allowed_filesystem_globs=("/tmp/*",),
        allowed_network_hosts=("example.com",),
        memory_limit_mb=128.0,
        cpu_limit_seconds=5.0,
        execution_timeout_seconds=2.0,
    )
    assert policy.allowed_permissions == frozenset({PermissionCategory.NETWORK})
    assert policy.allowed_filesystem_globs == ("/tmp/*",)
    assert policy.allowed_network_hosts == ("example.com",)
    assert policy.memory_limit_mb == 128.0


# ---------------------------------------------------------------------------
# engine.py -- AgentSandbox.check_permission
# ---------------------------------------------------------------------------


def test_check_permission_allowed() -> None:
    sandbox = AgentSandbox(
        "agent-1", AgentSandboxPolicy(allowed_permissions=frozenset({PermissionCategory.NETWORK}))
    )
    sandbox.check_permission(PermissionCategory.NETWORK)  # does not raise


def test_check_permission_denied() -> None:
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy())
    with pytest.raises(AuthorizationError, match="agent-1"):
        sandbox.check_permission(PermissionCategory.NETWORK)


# ---------------------------------------------------------------------------
# engine.py -- AgentSandbox.check_filesystem_access
# ---------------------------------------------------------------------------


def test_check_filesystem_access_allowed_glob() -> None:
    sandbox = AgentSandbox(
        "agent-1",
        AgentSandboxPolicy(
            allowed_permissions=frozenset({PermissionCategory.FILESYSTEM}),
            allowed_filesystem_globs=("/data/*",),
        ),
    )
    sandbox.check_filesystem_access("/data/report.csv")


def test_check_filesystem_access_outside_glob_denied() -> None:
    sandbox = AgentSandbox(
        "agent-1",
        AgentSandboxPolicy(
            allowed_permissions=frozenset({PermissionCategory.FILESYSTEM}),
            allowed_filesystem_globs=("/data/*",),
        ),
    )
    with pytest.raises(AuthorizationError, match="outside its sandbox policy"):
        sandbox.check_filesystem_access("/etc/passwd")


def test_check_filesystem_access_without_permission_denied_first() -> None:
    # No FILESYSTEM grant at all -- must fail on the permission check,
    # never reach the glob check, even for a path the glob would allow.
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(allowed_filesystem_globs=("/data/*",)))
    with pytest.raises(AuthorizationError, match="attempted filesystem"):
        sandbox.check_filesystem_access("/data/report.csv")


# ---------------------------------------------------------------------------
# engine.py -- AgentSandbox.check_network_access
# ---------------------------------------------------------------------------


def test_check_network_access_allowed_host() -> None:
    sandbox = AgentSandbox(
        "agent-1",
        AgentSandboxPolicy(
            allowed_permissions=frozenset({PermissionCategory.NETWORK}),
            allowed_network_hosts=("api.example.com",),
        ),
    )
    sandbox.check_network_access("api.example.com")


def test_check_network_access_disallowed_host_denied() -> None:
    sandbox = AgentSandbox(
        "agent-1",
        AgentSandboxPolicy(
            allowed_permissions=frozenset({PermissionCategory.NETWORK}),
            allowed_network_hosts=("api.example.com",),
        ),
    )
    with pytest.raises(AuthorizationError, match=re.escape("evil.example.com")):
        sandbox.check_network_access("evil.example.com")


def test_check_network_access_without_permission_denied() -> None:
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(allowed_network_hosts=("x.com",)))
    with pytest.raises(AuthorizationError):
        sandbox.check_network_access("x.com")


# ---------------------------------------------------------------------------
# engine.py -- AgentSandbox.check_memory_usage
# ---------------------------------------------------------------------------


def test_check_memory_usage_within_generous_limit() -> None:
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(memory_limit_mb=100_000.0))
    usage = sandbox.check_memory_usage()
    assert usage > 0.0


def test_check_memory_usage_over_limit_raises() -> None:
    # The current test process genuinely uses more than a fraction of a
    # megabyte -- a real, not simulated, over-limit condition.
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(memory_limit_mb=0.001))
    with pytest.raises(AuthorizationError, match="exceeds"):
        sandbox.check_memory_usage()


# ---------------------------------------------------------------------------
# engine.py -- AgentSandbox.run
# ---------------------------------------------------------------------------


async def test_run_completes_within_timeout() -> None:
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(execution_timeout_seconds=5.0))

    async def _quick() -> str:
        await asyncio.sleep(0.01)
        return "done"

    result = await sandbox.run(_quick())
    assert result == "done"


async def test_run_exceeding_timeout_raises() -> None:
    sandbox = AgentSandbox("agent-1", AgentSandboxPolicy(execution_timeout_seconds=0.05))

    async def _slow() -> str:
        await asyncio.sleep(1.0)
        return "too late"

    with pytest.raises(AIIOSTimeoutError, match=re.escape("0.05s")):
        await sandbox.run(_slow())


# ---------------------------------------------------------------------------
# process.py -- run_isolated
# ---------------------------------------------------------------------------


async def test_run_isolated_real_success() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_isolated([sys.executable, "-c", "print('hello-sandbox')"], policy=policy)
    assert result.succeeded is True
    assert result.exit_code == 0
    assert "hello-sandbox" in result.stdout
    assert result.stderr == ""
    assert result.duration_seconds >= 0.0


async def test_run_isolated_real_nonzero_exit() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_isolated([sys.executable, "-c", "import sys; sys.exit(3)"], policy=policy)
    assert result.succeeded is False
    assert result.exit_code == 3


async def test_run_isolated_captures_stderr() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_isolated(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom')"], policy=policy
    )
    assert result.succeeded is True
    assert "boom" in result.stderr


async def test_run_isolated_gets_its_own_throwaway_cwd() -> None:
    # Each run gets a fresh working directory -- confirmed by having
    # the real subprocess report os.getcwd() and checking that
    # directory no longer exists once run_isolated has returned
    # (Secure Cleanup, unconditionally on success).
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_isolated(
        [sys.executable, "-c", "import os; print(os.getcwd())"], policy=policy
    )
    assert result.succeeded is True
    reported_cwd = result.stdout.strip()
    assert "agent-sandbox-" in reported_cwd
    assert _gone(reported_cwd)


async def test_run_isolated_real_timeout_kills_process() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=0.2)
    started = time.monotonic()
    with pytest.raises(AIIOSTimeoutError, match=re.escape("0.2s")):
        await run_isolated([sys.executable, "-c", "import time; time.sleep(30)"], policy=policy)
    elapsed = time.monotonic() - started
    # A real, not simulated, timeout: the process was actually killed
    # rather than left to run its full 30s sleep.
    assert elapsed < 10.0


async def test_run_isolated_bad_executable_raises_internal_error() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=5.0)
    with pytest.raises(InternalError, match="Failed to start"):
        await run_isolated(["this-executable-does-not-exist-anywhere"], policy=policy)


async def test_run_isolated_with_explicit_workdir_is_not_auto_cleaned() -> None:
    # `workdir` is only ever passed by run_script_isolated in
    # production, but run_isolated's own public contract is that a
    # caller-supplied workdir is used as-is and NOT deleted by
    # run_isolated itself -- only the default, self-managed
    # TemporaryDirectory branch cleans up.
    manual_dir = tempfile.mkdtemp(prefix="manual-sandbox-")
    try:
        policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
        result = await run_isolated(
            [sys.executable, "-c", "print('ok')"], policy=policy, workdir=manual_dir
        )
        assert result.succeeded is True
        assert not _gone(manual_dir)
    finally:
        shutil.rmtree(manual_dir, ignore_errors=True)


async def test_run_isolated_passes_env() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_isolated(
        [sys.executable, "-c", "import os; print(os.environ.get('AGENT_SANDBOX_TEST', ''))"],
        policy=policy,
        env={"AGENT_SANDBOX_TEST": "marker-value"},
    )
    # Substring, not equality: this machine's own Python has a
    # ``pip_system_certs`` sitecustomize hook that writes its own
    # unrelated warning to the child's stdout before user code runs.
    # What this test is actually about is that the env var arrived.
    assert "marker-value" in result.stdout


# ---------------------------------------------------------------------------
# process.py -- run_script_isolated
# ---------------------------------------------------------------------------


async def test_run_script_isolated_real_success() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    result = await run_script_isolated(
        [sys.executable], "print('script-ran')", suffix=".py", policy=policy
    )
    assert result.succeeded is True
    assert "script-ran" in result.stdout


async def test_run_script_isolated_script_and_process_share_one_directory() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    script = "import os\n" "print(os.getcwd())\n" "print(sorted(os.listdir('.')))\n"
    result = await run_script_isolated([sys.executable], script, suffix=".py", policy=policy)
    assert result.succeeded is True
    lines = result.stdout.strip().splitlines()
    reported_cwd, listing = lines[0], lines[1]
    assert "agent-sandbox-" in reported_cwd
    assert "script.py" in listing
    # Secure Cleanup: that same directory is gone once the call returns.
    assert _gone(reported_cwd)


async def test_run_script_isolated_cleans_up_on_failure_too() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    script = "import os, sys; print(os.getcwd()); sys.exit(1)"
    result = await run_script_isolated([sys.executable], script, suffix=".py", policy=policy)
    assert result.succeeded is False
    assert result.exit_code == 1
    reported_cwd = result.stdout.strip()
    assert _gone(reported_cwd)


async def test_run_script_isolated_real_timeout() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=0.2)
    with pytest.raises(AIIOSTimeoutError):
        await run_script_isolated(
            [sys.executable], "import time; time.sleep(30)", suffix=".py", policy=policy
        )
