"""Python script runner. Per docs/040 "PLAYBOOK SUPPORT" "Python Scripts"."""

from __future__ import annotations

import sys

from app.runners.base import RunnerResult
from app.runners.subprocess_helper import run_script_file


async def run_python_script(
    content: str,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *content* as a real Python script under this interpreter's own executable.

    Raises:
        RunnerError: If the interpreter can't be spawned, or the process times out.
    """
    return await run_script_file(
        [sys.executable], content, suffix=".py", env=env, timeout_seconds=timeout_seconds
    )


__all__ = ["run_python_script"]
