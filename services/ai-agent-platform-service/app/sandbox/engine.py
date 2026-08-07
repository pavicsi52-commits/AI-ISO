"""Agent sandbox enforcement (docs/060 "SANDBOX").

Mirrors ``shared_core.plugins.sandbox.PluginSandbox``'s own capability-
check shape, but raises this platform's own *generic* exceptions
(``AuthorizationError``, ``AIIOSTimeoutError``) rather than plugin-
specific ones -- there is no dedicated ``AIIOS-AGENT-*`` sandbox
exception family, and none is needed: a sandbox violation *is* an
authorization failure (this agent was not granted that capability), and
an execution overrun *is* a timeout, both already modelled once at the
platform level.

True OS-level isolation (containers, seccomp, gVisor) is out of scope
for a portable, in-process Python library for the same reason it is
out of scope for the plugin sandbox this mirrors: real enforcement is
whatever process/container boundary a production deployment runs agent
tool calls under. This module implements the honestly achievable
layer: declared policy (:class:`~app.sandbox.policy.AgentSandboxPolicy`),
capability checks every tool-execution touchpoint must call before
acting, real execution-timeout enforcement, and best-effort process
memory monitoring via ``psutil``.
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

import psutil
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.timeout import AIIOSTimeoutError

from app.models.enums import PermissionCategory
from app.sandbox.policy import AgentSandboxPolicy

T = TypeVar("T")

_BYTES_PER_MB = 1024 * 1024


class AgentSandbox:
    """Enforces one agent's own :class:`AgentSandboxPolicy`."""

    def __init__(self, agent_slug: str, policy: AgentSandboxPolicy) -> None:
        self.agent_slug = agent_slug
        self.policy = policy

    def check_permission(self, category: PermissionCategory) -> None:
        """Raise unless *category* is within this sandbox's allowed set.

        Raises:
            AuthorizationError: If *category* isn't allowed.
        """
        if category not in self.policy.allowed_permissions:
            raise AuthorizationError(
                f"Agent {self.agent_slug!r} attempted {category!s}, "
                "which its sandbox policy does not allow."
            )

    def check_filesystem_access(self, path: str | Path) -> None:
        """Raise unless *path* matches one of this sandbox's allowed
        filesystem globs.

        Raises:
            AuthorizationError: If ``FILESYSTEM`` isn't granted, or
                *path* isn't covered by any allowed glob.
        """
        self.check_permission(PermissionCategory.FILESYSTEM)
        text = str(Path(path))
        if not any(fnmatch.fnmatch(text, glob) for glob in self.policy.allowed_filesystem_globs):
            raise AuthorizationError(
                f"Agent {self.agent_slug!r} attempted filesystem access to {text!r}, "
                "outside its sandbox policy."
            )

    def check_network_access(self, host: str) -> None:
        """Raise unless *host* is in this sandbox's allowed network hosts.

        Raises:
            AuthorizationError: If ``NETWORK`` isn't granted, or *host*
                isn't allowed.
        """
        self.check_permission(PermissionCategory.NETWORK)
        if host not in self.policy.allowed_network_hosts:
            raise AuthorizationError(
                f"Agent {self.agent_slug!r} attempted network access to {host!r}, "
                "outside its sandbox policy."
            )

    def check_memory_usage(self) -> float:
        """Return current process RSS memory usage in MB, raising if over policy.

        Best-effort monitoring, not prevention or per-agent accounting
        -- reports this whole process's memory against
        ``policy.memory_limit_mb``, since no per-agent measurement
        exists without OS-level process isolation ("Memory Limits").

        Raises:
            AuthorizationError: If usage exceeds the configured limit.
        """
        usage_mb = psutil.Process().memory_info().rss / _BYTES_PER_MB
        if usage_mb > self.policy.memory_limit_mb:
            raise AuthorizationError(
                f"Agent {self.agent_slug!r} process memory usage {usage_mb:.1f}MB exceeds "
                f"its {self.policy.memory_limit_mb}MB sandbox limit."
            )
        return usage_mb

    async def run(self, awaitable: Awaitable[T]) -> T:
        """Run *awaitable* under this sandbox's execution timeout
        ("Execution Timeout").

        Raises:
            AIIOSTimeoutError: If *awaitable* exceeds
                ``policy.execution_timeout_seconds``.
        """
        try:
            return await asyncio.wait_for(awaitable, timeout=self.policy.execution_timeout_seconds)
        except TimeoutError as exc:
            raise AIIOSTimeoutError(
                f"Agent {self.agent_slug!r} exceeded its "
                f"{self.policy.execution_timeout_seconds}s sandbox execution timeout."
            ) from exc


__all__ = ["AgentSandbox"]
