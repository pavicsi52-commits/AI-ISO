"""Isolated local-process execution (docs/060 "SANDBOX": Process
Isolation, Artifact Isolation, Secure Cleanup).

Mirrors ``automation-service``'s own ``app/runners/subprocess_helper
.run_argv``/``run_script_file`` (a real local process via
``asyncio.create_subprocess_exec``, never ``shell=True``, so no shell-
injection surface from interpolated content) and adds what an agent's
own Shell/Python tool calls additionally need beyond a one-off
automation script run:

- **Artifact Isolation** -- every run gets its own throwaway working
  directory, so one tool call can never read or clobber another's
  files by writing to a shared cwd.
- **Secure Cleanup** -- that directory is deleted afterward
  unconditionally, success or failure, so no tool call leaves files
  behind on the host.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from shared_core.exceptions.service import InternalError
from shared_core.exceptions.timeout import AIIOSTimeoutError

from app.sandbox.policy import AgentSandboxPolicy


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    """The outcome of one isolated local process run."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Whether the process exited with status 0."""
        return self.exit_code == 0


async def run_isolated(
    argv: Sequence[str],
    *,
    policy: AgentSandboxPolicy,
    env: dict[str, str] | None = None,
    workdir: str | None = None,
) -> SandboxExecutionResult:
    """Run *argv* as a real local process inside a fresh, throwaway
    working directory, enforcing ``policy.execution_timeout_seconds``.

    *workdir* is only ever passed by :func:`run_script_isolated`, so a
    script and the process running it share the one directory that
    gets cleaned up; every other caller gets its own fresh directory.

    Raises:
        InternalError: If the process can't be spawned.
        AIIOSTimeoutError: If the process exceeds
            ``policy.execution_timeout_seconds``.
    """
    if workdir is not None:
        return await _spawn_and_wait(argv, cwd=workdir, policy=policy, env=env)

    with tempfile.TemporaryDirectory(prefix="agent-sandbox-") as isolated_dir:
        return await _spawn_and_wait(argv, cwd=isolated_dir, policy=policy, env=env)
    # `with` block exit deletes `isolated_dir` unconditionally -- Secure
    # Cleanup, even when spawning or waiting raised above.


async def run_script_isolated(
    interpreter: Sequence[str],
    content: str,
    *,
    suffix: str,
    policy: AgentSandboxPolicy,
    env: dict[str, str] | None = None,
) -> SandboxExecutionResult:
    """Write *content* to a file inside a fresh, throwaway working
    directory and run it under *interpreter* there.

    Unlike a bare temp file dropped into the system temp directory,
    the script itself lives inside the same isolated, cleaned-up
    directory its own process runs in -- so a script that reads its own
    source, or writes sibling artifact files, still only ever touches
    that one throwaway directory.

    Raises:
        InternalError: If the interpreter can't be spawned.
        AIIOSTimeoutError: If the process exceeds
            ``policy.execution_timeout_seconds``.
    """
    with tempfile.TemporaryDirectory(prefix="agent-sandbox-") as isolated_dir:
        script_path = Path(isolated_dir) / f"script{suffix}"
        script_path.write_text(content, encoding="utf-8")
        return await run_isolated(
            [*interpreter, str(script_path)], policy=policy, env=env, workdir=isolated_dir
        )


async def _spawn_and_wait(
    argv: Sequence[str],
    *,
    cwd: str,
    policy: AgentSandboxPolicy,
    env: dict[str, str] | None,
) -> SandboxExecutionResult:
    """Spawn *argv* in *cwd* and enforce the sandbox's own execution
    timeout -- the one place both public entry points ultimately call
    into.
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
        raise InternalError(f"Failed to start {argv[0]!r} in the agent sandbox: {exc}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=policy.execution_timeout_seconds
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise AIIOSTimeoutError(
            f"{argv[0]!r} exceeded its {policy.execution_timeout_seconds}s "
            "agent sandbox execution timeout."
        ) from exc

    duration = time.perf_counter() - start
    return SandboxExecutionResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        duration_seconds=duration,
    )


__all__ = ["SandboxExecutionResult", "run_isolated", "run_script_isolated"]
