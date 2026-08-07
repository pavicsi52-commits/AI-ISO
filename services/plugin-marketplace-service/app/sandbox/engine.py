"""Plugin execution sandbox (docs/059 "SANDBOX").

Reuses ``shared_core.plugins.sandbox.PluginSandbox``/``SandboxPolicy``
for exactly the pieces that are genuinely permission-vocabulary-agnostic:
real execution-timeout enforcement (``PluginSandbox.run``, an
``asyncio.wait_for`` wrapper) and best-effort process-wide memory
monitoring (``PluginSandbox.check_memory_usage``, via ``psutil``).

Capability checks are deliberately **not** delegated to
``PluginSandbox.check_permission``/``check_filesystem_access``/
``check_network_access`` -- those are keyed to
``shared_core.plugins.permissions.PluginPermission`` (nine values:
FILESYSTEM/DATABASE/NETWORK/WORKFLOW/CONNECTOR/AI/NOTIFICATIONS/
SCHEDULER/STORAGE), which does not cover this service's own eleven-value
``PluginPermissionCategory`` (docs/059's literal Inventory/Automation/
Workflow/Secrets/Knowledge-Graph/Monitoring/Notification/API/Filesystem/
Network/Custom taxonomy, persisted per-installation in
``plugin_permissions``). Forcing an enum bridge between two vocabularies
that only partially overlap would be more fragile than it's worth, so
capability/filesystem/network checks here are bespoke, keyed to
``PluginPermissionCategory`` directly.

Real local-process execution (``asyncio.create_subprocess_exec``, never
``shell=True``), the same isolated-OS-process-with-a-real-timeout-kill
pattern ``automation-service/app/runners/subprocess_helper.py`` already
established -- reimplemented here, not imported, per this platform's
zero-cross-service-import convention.
"""

from __future__ import annotations

import asyncio
import fnmatch
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy

from app.models.enums import PluginPermissionCategory


class SandboxViolationError(Exception):
    """A sandboxed plugin attempted something outside its own granted policy."""


class SandboxExecutionError(Exception):
    """A sandboxed plugin process could not be started."""


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    """The outcome of running one sandboxed plugin process."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool


@dataclass(frozen=True, slots=True)
class PluginExecutionPolicy:
    """What one installed plugin instance is allowed to touch, and its
    resource limits -- keyed to this service's own
    ``PluginPermissionCategory``, not ``shared_core``'s.
    """

    granted_categories: frozenset[PluginPermissionCategory] = field(default_factory=frozenset)
    allowed_filesystem_globs: tuple[str, ...] = ()
    allowed_network_hosts: tuple[str, ...] = ()
    memory_limit_mb: float = 256.0
    execution_timeout_seconds: float = 60.0


class PluginExecutionSandbox:
    """Enforces one installed plugin instance's own :class:`PluginExecutionPolicy`."""

    def __init__(self, plugin_installation_id: str, policy: PluginExecutionPolicy) -> None:
        self._plugin_installation_id = plugin_installation_id
        self.policy = policy
        self._timeout_sandbox = PluginSandbox(
            plugin_installation_id,
            SandboxPolicy(
                memory_limit_mb=policy.memory_limit_mb,
                execution_timeout_seconds=policy.execution_timeout_seconds,
            ),
        )

    def check_granted(self, category: PluginPermissionCategory) -> None:
        """Raise unless *category* is within this sandbox's granted set.

        Raises:
            SandboxViolationError: If *category* isn't granted.
        """
        if category not in self.policy.granted_categories:
            raise SandboxViolationError(
                f"Plugin installation {self._plugin_installation_id!r} attempted "
                f"{category.value!r}, which has not been granted."
            )

    def check_filesystem_access(self, path: str) -> None:
        """Raise unless *path* matches one of this sandbox's allowed filesystem globs.

        Raises:
            SandboxViolationError: If FILESYSTEM isn't granted, or *path*
                isn't covered by any allowed glob.
        """
        self.check_granted(PluginPermissionCategory.FILESYSTEM)
        if not any(fnmatch.fnmatch(path, glob) for glob in self.policy.allowed_filesystem_globs):
            raise SandboxViolationError(
                f"Plugin installation {self._plugin_installation_id!r} attempted filesystem "
                f"access to {path!r}, outside its sandbox policy."
            )

    def check_network_access(self, host: str) -> None:
        """Raise unless *host* is in this sandbox's allowed network hosts.

        Raises:
            SandboxViolationError: If NETWORK isn't granted, or *host*
                isn't allowed.
        """
        self.check_granted(PluginPermissionCategory.NETWORK)
        if host not in self.policy.allowed_network_hosts:
            raise SandboxViolationError(
                f"Plugin installation {self._plugin_installation_id!r} attempted network "
                f"access to {host!r}, outside its sandbox policy."
            )

    def check_memory_usage(self) -> float:
        """Return current process RSS memory usage in MB, raising if over policy.

        Raises:
            SandboxViolationError: If usage exceeds the configured limit.
        """
        try:
            return self._timeout_sandbox.check_memory_usage()
        except Exception as exc:
            raise SandboxViolationError(str(exc)) from exc

    async def run_entry_point(
        self,
        argv: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxExecutionResult:
        """Spawn *argv* as a real local process, killing it if it exceeds
        this sandbox's own ``policy.execution_timeout_seconds``.

        Raises:
            SandboxExecutionError: If the process cannot be spawned.
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
            raise SandboxExecutionError(
                f"Plugin installation {self._plugin_installation_id!r} failed to start "
                f"{argv[0]!r}: {exc}"
            ) from exc

        timed_out = False
        stdout_bytes = b""
        stderr_bytes = b""
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self.policy.execution_timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            await process.wait()

        return SandboxExecutionResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_seconds=time.perf_counter() - start,
            timed_out=timed_out,
        )


__all__ = [
    "PluginExecutionPolicy",
    "PluginExecutionSandbox",
    "SandboxExecutionError",
    "SandboxExecutionResult",
    "SandboxViolationError",
]
