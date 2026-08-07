"""Agent sandbox policy (docs/060 "SANDBOX").

Mirrors ``shared_core.plugins.sandbox.SandboxPolicy``'s own shape, keyed
to this service's own :class:`~app.models.enums.PermissionCategory`
rather than ``shared_core.plugins.permissions.PluginPermission`` --
the same "don't force an enum bridge between partially-overlapping
vocabularies" call already made for plugin-marketplace-service's own
sandbox (Prompt 059). A plugin's permission vocabulary (filesystem,
network, database, secrets, ...) and an agent's (tool invocation, data
access, model access, delegation, ...) only partly overlap; bridging
them would either lose meaning on one side or force fields neither
domain actually has.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import PermissionCategory

DEFAULT_MEMORY_LIMIT_MB = 512.0
DEFAULT_CPU_LIMIT_SECONDS = 30.0
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class AgentSandboxPolicy:
    """What one agent (or one of its tool calls) is allowed to touch,
    and its resource limits.

    ``cpu_limit_seconds`` is declared and reported, not enforced -- no
    in-process Python sandbox can cap CPU time without an OS/container
    boundary underneath it (``resource.setrlimit`` isn't even available
    on Windows). Real CPU enforcement is whatever process/container
    boundary a production deployment runs agent tool calls under; this
    field is the policy that boundary is configured from.
    """

    allowed_permissions: frozenset[PermissionCategory] = field(default_factory=frozenset)
    allowed_filesystem_globs: tuple[str, ...] = ()
    allowed_network_hosts: tuple[str, ...] = ()
    memory_limit_mb: float = DEFAULT_MEMORY_LIMIT_MB
    cpu_limit_seconds: float = DEFAULT_CPU_LIMIT_SECONDS
    execution_timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS


__all__ = [
    "DEFAULT_CPU_LIMIT_SECONDS",
    "DEFAULT_EXECUTION_TIMEOUT_SECONDS",
    "DEFAULT_MEMORY_LIMIT_MB",
    "AgentSandboxPolicy",
]
