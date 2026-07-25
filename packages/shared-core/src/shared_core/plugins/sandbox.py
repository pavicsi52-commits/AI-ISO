"""Plugin sandbox.

Per docs/029_Enterprise_Plugin_Framework.md.txt "SANDBOX": Isolate
plugins. Restrict Filesystem, Network, Database, Secrets, Environment
Variables, OS Commands, Memory Limits, CPU Limits, Execution Time.

True OS-level isolation (containers, seccomp, gVisor) is out of scope
for a portable, in-process Python library -- `resource.setrlimit` isn't
even available on Windows, and no in-process sandbox can fully contain
arbitrary Python bytecode without an OS/container boundary underneath
it (the same reason this codebase's expression sandboxes, e.g.
:mod:`shared_core.workflow.expressions`, only ever sandbox *expressions*,
never arbitrary plugin code). This module implements the honestly
achievable layer instead: declared policy (:class:`SandboxPolicy`),
capability checks every framework touchpoint (permissions, filesystem
paths, network hosts) must call before acting, real execution-timeout
enforcement (the same ``asyncio.wait_for`` mechanism every other
Prompt 021-028 framework's own ``with_timeout`` uses), and best-effort
process memory monitoring via ``psutil`` (already a dependency) --
process-wide, not per-plugin, since without OS-level process isolation
there is no true per-plugin memory accounting. CPU limits stay a
declared, advisory policy field only (enforced by whatever real process/
container boundary a production deployment runs plugins under).
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import psutil

from shared_core.plugins.constants import (
    DEFAULT_CPU_LIMIT_SECONDS,
    DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    DEFAULT_MEMORY_LIMIT_MB,
)
from shared_core.plugins.exceptions import PluginExecutionTimeoutError, SandboxViolationError
from shared_core.plugins.permissions import PluginPermission

T = TypeVar("T")

_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """What one plugin is allowed to touch, and its resource limits."""

    allowed_permissions: frozenset[PluginPermission] = field(default_factory=frozenset)
    allowed_filesystem_globs: tuple[str, ...] = ()
    allowed_network_hosts: tuple[str, ...] = ()
    memory_limit_mb: float = DEFAULT_MEMORY_LIMIT_MB
    cpu_limit_seconds: float = DEFAULT_CPU_LIMIT_SECONDS
    execution_timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS


class PluginSandbox:
    """Enforces one plugin's :class:`SandboxPolicy`."""

    def __init__(self, plugin_id: str, policy: SandboxPolicy) -> None:
        self.plugin_id = plugin_id
        self.policy = policy

    def check_permission(self, permission: PluginPermission) -> None:
        """Raise unless *permission* is within this sandbox's allowed set.

        Raises:
            SandboxViolationError: If *permission* isn't allowed.
        """
        if permission not in self.policy.allowed_permissions:
            raise SandboxViolationError(
                f"Plugin {self.plugin_id!r} attempted {permission.value!r}, "
                "which its sandbox policy does not allow."
            )

    def check_filesystem_access(self, path: str | Path) -> None:
        """Raise unless *path* matches one of this sandbox's allowed filesystem globs.

        Raises:
            SandboxViolationError: If ``FILESYSTEM`` isn't granted, or
                *path* isn't covered by any allowed glob.
        """
        self.check_permission(PluginPermission.FILESYSTEM)
        text = str(Path(path))
        if not any(fnmatch.fnmatch(text, glob) for glob in self.policy.allowed_filesystem_globs):
            raise SandboxViolationError(
                f"Plugin {self.plugin_id!r} attempted filesystem access to {text!r}, "
                "outside its sandbox policy."
            )

    def check_network_access(self, host: str) -> None:
        """Raise unless *host* is in this sandbox's allowed network hosts.

        Raises:
            SandboxViolationError: If ``NETWORK`` isn't granted, or
                *host* isn't allowed.
        """
        self.check_permission(PluginPermission.NETWORK)
        if host not in self.policy.allowed_network_hosts:
            raise SandboxViolationError(
                f"Plugin {self.plugin_id!r} attempted network access to {host!r}, "
                "outside its sandbox policy."
            )

    def check_memory_usage(self) -> float:
        """Return current process RSS memory usage in MB, raising if over policy.

        Best-effort monitoring, not prevention or per-plugin accounting
        -- reports this whole process's memory against
        ``policy.memory_limit_mb``, since no per-plugin measurement
        exists without OS-level process isolation ("Memory Limits").

        Raises:
            SandboxViolationError: If usage exceeds the configured limit.
        """
        usage_mb = psutil.Process().memory_info().rss / _BYTES_PER_MB
        if usage_mb > self.policy.memory_limit_mb:
            raise SandboxViolationError(
                f"Plugin {self.plugin_id!r} process memory usage {usage_mb:.1f}MB exceeds "
                f"its {self.policy.memory_limit_mb}MB sandbox limit."
            )
        return usage_mb

    async def run(self, awaitable: Awaitable[T]) -> T:
        """Run *awaitable* under this sandbox's execution timeout ("Execution Time").

        Raises:
            PluginExecutionTimeoutError: If *awaitable* exceeds
                ``policy.execution_timeout_seconds``.
        """
        try:
            return await asyncio.wait_for(awaitable, timeout=self.policy.execution_timeout_seconds)
        except TimeoutError as exc:
            raise PluginExecutionTimeoutError(
                f"Plugin {self.plugin_id!r} exceeded its "
                f"{self.policy.execution_timeout_seconds}s execution timeout."
            ) from exc


__all__ = ["PluginSandbox", "SandboxPolicy"]
