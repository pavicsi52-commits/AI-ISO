"""The result shape every local script/playbook runner returns.

Deliberately mirrors :class:`shared_core.connectors.base.CommandResult`
(the shape a *remote* connector's own ``execute()`` returns) so the
execution service can treat a local runner's outcome and a remote
connector's outcome identically once wrapped into one
:class:`~app.models.automation_execution_step.AutomationExecutionStep`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunnerResult:
    """The outcome of one local script/playbook run."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Whether the process exited with status 0."""
        return self.exit_code == 0


__all__ = ["RunnerResult"]
