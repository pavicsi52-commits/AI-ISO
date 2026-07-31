"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.catalogue import (
    ControlMappingRepository,
    ControlRepository,
    FrameworkRepository,
)
from app.repositories.governance import (
    AuditRepository,
    ExceptionRepository,
    FindingRepository,
    HistoryRepository,
    RemediationRepository,
    ReportRepository,
    RiskRepository,
    ScoreRepository,
    StatisticRepository,
)
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)

__all__ = [
    "AssessmentRepository",
    "AuditRepository",
    "ControlMappingRepository",
    "ControlRepository",
    "EvidenceRepository",
    "ExceptionRepository",
    "FindingRepository",
    "FrameworkRepository",
    "HistoryRepository",
    "RemediationRepository",
    "ReportRepository",
    "ResultRepository",
    "RiskRepository",
    "ScanRepository",
    "ScoreRepository",
    "StatisticRepository",
]
