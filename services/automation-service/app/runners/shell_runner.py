"""POSIX shell (``sh``) script runner. Per docs/040 "PLAYBOOK SUPPORT"
"Shell Scripts", distinct from :mod:`app.runners.bash_runner`'s own
``bash``-specific "Bash" entry.
"""

from __future__ import annotations

from app.runners.base import RunnerResult
from app.runners.subprocess_helper import run_script_file


async def run_shell_script(
    content: str,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *content* as a real ``sh`` script.

    Raises:
        RunnerError: If ``sh`` can't be spawned, or the process times out.
    """
    return await run_script_file(
        ["sh"], content, suffix=".sh", env=env, timeout_seconds=timeout_seconds
    )


__all__ = ["run_shell_script"]
