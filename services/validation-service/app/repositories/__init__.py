"""Repositories for the validation service's 17 tables."""

from __future__ import annotations

from app.repositories.validation_audit import ValidationAuditEntryRepository
from app.repositories.validation_category import ValidationCategoryRepository
from app.repositories.validation_check import ValidationCheckRepository
from app.repositories.validation_exception import ValidationExceptionRepository
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_remediation import ValidationRemediationRepository
from app.repositories.validation_report import ValidationReportRepository
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_result_detail import ValidationResultDetailRepository
from app.repositories.validation_rule import ValidationRuleRepository
from app.repositories.validation_score import ValidationScoreRepository
from app.repositories.validation_statistics import ValidationStatisticsRepository
from app.repositories.validation_target import ValidationTargetRepository
from app.repositories.validation_template import ValidationTemplateRepository

__all__ = [
    "ValidationAuditEntryRepository",
    "ValidationCategoryRepository",
    "ValidationCheckRepository",
    "ValidationExceptionRepository",
    "ValidationExecutionRepository",
    "ValidationFailureRepository",
    "ValidationHistoryRepository",
    "ValidationProfileRepository",
    "ValidationRemediationRepository",
    "ValidationReportRepository",
    "ValidationResultDetailRepository",
    "ValidationResultRepository",
    "ValidationRuleRepository",
    "ValidationScoreRepository",
    "ValidationStatisticsRepository",
    "ValidationTargetRepository",
    "ValidationTemplateRepository",
]
