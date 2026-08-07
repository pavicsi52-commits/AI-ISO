"""Multi-agent orchestration (docs/060 "MULTI-AGENT ORCHESTRATION")."""

from __future__ import annotations

from app.agents.orchestrator import (
    AgentOrchestrator,
    AgentResult,
    AgentTask,
    SharedMemory,
    aggregate,
    decompose,
    route,
    select_dynamically,
)
from app.agents.patterns import (
    run_conflict_resolution,
    run_delegation,
    run_hierarchical,
    run_peer_to_peer,
    run_planner_executor,
    run_supervised,
)

__all__ = [
    "AgentOrchestrator",
    "AgentResult",
    "AgentTask",
    "SharedMemory",
    "aggregate",
    "decompose",
    "route",
    "run_conflict_resolution",
    "run_delegation",
    "run_hierarchical",
    "run_peer_to_peer",
    "run_planner_executor",
    "run_supervised",
    "select_dynamically",
]
