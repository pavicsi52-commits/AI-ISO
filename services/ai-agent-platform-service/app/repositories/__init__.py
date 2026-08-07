"""Repositories: one per table (docs/060's own 17-table schema)."""

from __future__ import annotations

from app.repositories.agent import AgentRepository, AgentVersionRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.evaluation import AgentEvaluationRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.governance import (
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from app.repositories.guardrail import AgentGuardrailRepository
from app.repositories.marketplace import AgentMarketplaceEntryRepository
from app.repositories.memory import AgentMemoryRepository
from app.repositories.permission import AgentPermissionGrantRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.session import AgentSessionRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.tool import AgentToolRepository
from app.repositories.workflow import AgentWorkflowRepository

__all__ = [
    "AgentAuditRepository",
    "AgentBenchmarkRepository",
    "AgentEvaluationRepository",
    "AgentExecutionRepository",
    "AgentGuardrailRepository",
    "AgentMarketplaceEntryRepository",
    "AgentMemoryRepository",
    "AgentPermissionGrantRepository",
    "AgentProfileRepository",
    "AgentReportRepository",
    "AgentRepository",
    "AgentSessionRepository",
    "AgentStatisticRepository",
    "AgentTaskRepository",
    "AgentToolRepository",
    "AgentVersionRepository",
    "AgentWorkflowRepository",
]
