"""Agent execution sandbox (docs/060 "SANDBOX")."""

from __future__ import annotations

from app.sandbox.engine import AgentSandbox
from app.sandbox.policy import AgentSandboxPolicy
from app.sandbox.process import SandboxExecutionResult, run_isolated, run_script_isolated

__all__ = [
    "AgentSandbox",
    "AgentSandboxPolicy",
    "SandboxExecutionResult",
    "run_isolated",
    "run_script_isolated",
]
