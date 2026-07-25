"""Tests for every local script/playbook runner -- real subprocess
execution against the host's own interpreters, no mocking.
"""

from __future__ import annotations

import sys

import pytest

from app.runners.ansible_runner import is_ansible_available, run_ansible_playbook
from app.runners.bash_runner import run_bash_script
from app.runners.exceptions import RunnerError
from app.runners.powershell_runner import run_powershell_script
from app.runners.python_runner import run_python_script
from app.runners.shell_runner import run_shell_script
from app.runners.subprocess_helper import run_argv, run_script_file


class TestShellRunner:
    async def test_runs_real_shell_script(self) -> None:
        result = await run_shell_script("echo hello-shell")
        assert result.succeeded
        assert result.exit_code == 0
        assert "hello-shell" in result.stdout

    async def test_nonzero_exit_is_not_success(self) -> None:
        result = await run_shell_script("exit 3")
        assert result.exit_code == 3
        assert not result.succeeded


class TestBashRunner:
    async def test_runs_real_bash_script(self) -> None:
        result = await run_bash_script("echo hello-bash")
        assert result.succeeded
        assert "hello-bash" in result.stdout

    async def test_captures_stderr(self) -> None:
        result = await run_bash_script("echo oops 1>&2; exit 1")
        assert not result.succeeded
        assert "oops" in result.stderr


class TestPythonRunner:
    async def test_runs_real_python_script(self) -> None:
        result = await run_python_script("print('hello-python')")
        assert result.succeeded
        assert "hello-python" in result.stdout

    async def test_python_exception_fails(self) -> None:
        result = await run_python_script("raise RuntimeError('boom')")
        assert not result.succeeded
        assert "boom" in result.stderr

    async def test_duration_is_measured(self) -> None:
        result = await run_python_script("print('x')")
        assert result.duration_seconds >= 0.0


class TestPowershellRunner:
    async def test_runs_real_powershell_script(self) -> None:
        result = await run_powershell_script("Write-Output 'hello-powershell'")
        assert result.succeeded
        assert "hello-powershell" in result.stdout


class TestAnsibleRunner:
    def test_is_ansible_available_reflects_path(self) -> None:
        assert isinstance(is_ansible_available(), bool)

    async def test_raises_when_ansible_not_installed(self) -> None:
        if is_ansible_available():
            pytest.skip("ansible-playbook is installed on this host.")
        with pytest.raises(RunnerError, match="not available on PATH"):
            await run_ansible_playbook("- hosts: all\n  tasks: []\n", inventory_hosts=["localhost"])


class TestSubprocessHelper:
    async def test_run_argv_captures_stdout(self) -> None:
        result = await run_argv([sys.executable, "-c", "print('argv-ok')"])
        assert result.succeeded
        assert "argv-ok" in result.stdout

    async def test_run_argv_raises_for_missing_binary(self) -> None:
        with pytest.raises(RunnerError, match="Failed to start"):
            await run_argv(["definitely-not-a-real-binary-xyz"])

    async def test_run_argv_times_out(self) -> None:
        with pytest.raises(RunnerError, match="timed out"):
            await run_argv(
                [sys.executable, "-c", "import time; time.sleep(5)"], timeout_seconds=0.1
            )

    async def test_run_script_file_cleans_up_temp_file(self) -> None:
        result = await run_script_file([sys.executable], "print('cleanup-ok')", suffix=".py")
        assert result.succeeded
        assert "cleanup-ok" in result.stdout
