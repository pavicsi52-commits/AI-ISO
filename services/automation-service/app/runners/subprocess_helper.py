"""Shared local-subprocess execution helper for every script/shell/
playbook runner in this package. Every runner spawns a genuine local
process (``asyncio.create_subprocess_exec``, never ``shell=True``, so
no shell-injection surface from interpolated content) -- real local
execution, not a simulation, the same "real code, locally testable"
precedent every prior AI-IOS prompt's own locally-executable capability
established.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from app.runners.base import RunnerResult
from app.runners.exceptions import RunnerError


async def run_argv(
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *argv* as a real local process and capture its real output.

    Raises:
        RunnerError: If the process can't be spawned, or exceeds
            *timeout_seconds*.
    """
    start = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
    except OSError as exc:
        raise RunnerError(f"Failed to start {argv[0]!r}: {exc}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RunnerError(f"{argv[0]!r} timed out after {timeout_seconds}s.") from exc

    duration = time.perf_counter() - start
    return RunnerResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        duration_seconds=duration,
    )


async def run_script_file(
    interpreter: Sequence[str],
    content: str,
    *,
    suffix: str,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Write *content* to a real temporary file and run it under *interpreter*.

    Raises:
        RunnerError: If the interpreter can't be spawned, or the
            process exceeds *timeout_seconds*.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as handle:
        handle.write(content)
        script_path = Path(handle.name)
    try:
        return await run_argv(
            [*interpreter, str(script_path)], env=env, timeout_seconds=timeout_seconds
        )
    finally:
        await asyncio.to_thread(script_path.unlink, missing_ok=True)


__all__ = ["run_argv", "run_script_file"]
