"""Every repository this service uses."""

from __future__ import annotations

from app.repositories.policy import (
    PolicyAttributeRepository,
    PolicyCategoryRepository,
    PolicyConditionRepository,
    PolicyRepository,
    PolicyRuleRepository,
    PolicyVersionRepository,
)
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyAuditRepository,
    PolicyDecisionRepository,
    PolicyExceptionRepository,
    PolicyQuotaRepository,
    PolicyReportRepository,
    PolicySimulationRepository,
    PolicyStatisticsRepository,
    PolicyViolationRepository,
)

__all__ = [
    "PolicyApprovalRepository",
    "PolicyAttributeRepository",
    "PolicyAuditRepository",
    "PolicyCategoryRepository",
    "PolicyConditionRepository",
    "PolicyDecisionRepository",
    "PolicyExceptionRepository",
    "PolicyQuotaRepository",
    "PolicyReportRepository",
    "PolicyRepository",
    "PolicyRuleRepository",
    "PolicySimulationRepository",
    "PolicyStatisticsRepository",
    "PolicyVersionRepository",
    "PolicyViolationRepository",
]
