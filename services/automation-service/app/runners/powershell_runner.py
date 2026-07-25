"""PowerShell script runner. Per docs/040 "PLAYBOOK SUPPORT"
"PowerShell". Prefers PowerShell Core (``pwsh``, cross-platform, the
realistic choice for this service's own Linux container deployment
target) and falls back to Windows PowerShell (``powershell.exe``) when
that's what's actually on ``PATH`` -- e.g. this project's own Windows
development machine, which has no ``pwsh`` installed.
"""

from __future__ import annotations

import shutil

from app.runners.base import RunnerResult
from app.runners.exceptions import RunnerError
from app.runners.subprocess_helper import run_script_file


def _resolve_powershell_argv() -> list[str]:
    if shutil.which("pwsh") is not None:
        return ["pwsh", "-NoProfile", "-NonInteractive", "-File"]
    if shutil.which("powershell.exe") is not None:
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-File"]
    raise RunnerError("Neither 'pwsh' nor 'powershell.exe' is available on PATH.")


async def run_powershell_script(
    content: str,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> RunnerResult:
    """Run *content* as a real PowerShell script.

    Raises:
        RunnerError: If neither ``pwsh`` nor ``powershell.exe`` is
            available, or the process times out.
    """
    interpreter = _resolve_powershell_argv()
    return await run_script_file(
        interpreter, content, suffix=".ps1", env=env, timeout_seconds=timeout_seconds
    )


__all__ = ["run_powershell_script"]
