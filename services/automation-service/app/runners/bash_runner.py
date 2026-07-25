"""Bash script runner. Per docs/040 "PLAYBOOK SUPPORT" "Bash", distinct
from :mod:`app.runners.shell_runner`'s own POSIX-``sh`` "Shell
Scripts" entry.
"""

from __future__ import annotations

from app.runners.base import RunnerResult
from app.runners.subprocess_helper import run_script_file


async def run_bash_script(
    content: str,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *content* as a real ``bash`` script.

    Raises:
        RunnerError: If ``bash`` can't be spawned, or the process times out.
    """
    return await run_script_file(
        ["bash"], content, suffix=".sh", env=env, timeout_seconds=timeout_seconds
    )


__all__ = ["run_bash_script"]
