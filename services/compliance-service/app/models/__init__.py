"""Every table this service owns.

Imported as a package by Alembic's ``env.py``, which is what registers
each model with ``Base.metadata`` before autogenerate runs. A model not
re-exported here is a table the migration will not know about.
"""

from __future__ import annotations

from app.models.assessment import ComplianceAssessment, ComplianceResult, ComplianceScan
from app.models.evidence import ComplianceEvidence, ComplianceException, ComplianceFinding
from app.models.framework import ComplianceControl, ComplianceFramework, ControlMapping
from app.models.governance import (
    ComplianceAudit,
    ComplianceHistory,
    ComplianceReport,
    ComplianceScore,
    ComplianceStatistic,
    RemediationTask,
    RiskRegisterEntry,
)

__all__ = [
    "ComplianceAssessment",
    "ComplianceAudit",
    "ComplianceControl",
    "ComplianceEvidence",
    "ComplianceException",
    "ComplianceFinding",
    "ComplianceFramework",
    "ComplianceHistory",
    "ComplianceReport",
    "ComplianceResult",
    "ComplianceScan",
    "ComplianceScore",
    "ComplianceStatistic",
    "ControlMapping",
    "RemediationTask",
    "RiskRegisterEntry",
]
