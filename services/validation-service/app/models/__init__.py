"""SQLAlchemy models for the validation service's 17 tables."""

from __future__ import annotations

from app.models.validation_audit import ValidationAuditEntry
from app.models.validation_category import ValidationCategory
from app.models.validation_check import ValidationCheck
from app.models.validation_exception import ValidationException
from app.models.validation_execution import ValidationExecution
from app.models.validation_failure import ValidationFailure
from app.models.validation_history import ValidationHistory
from app.models.validation_profile import ValidationProfile
from app.models.validation_remediation import ValidationRemediation
from app.models.validation_report import ValidationReport
from app.models.validation_result import ValidationResult
from app.models.validation_result_detail import ValidationResultDetail
from app.models.validation_rule import ValidationRule
from app.models.validation_score import ValidationScore
from app.models.validation_statistics import ValidationStatistics
from app.models.validation_target import ValidationTarget
from app.models.validation_template import ValidationTemplate

__all__ = [
    "ValidationAuditEntry",
    "ValidationCategory",
    "ValidationCheck",
    "ValidationException",
    "ValidationExecution",
    "ValidationFailure",
    "ValidationHistory",
    "ValidationProfile",
    "ValidationRemediation",
    "ValidationReport",
    "ValidationResult",
    "ValidationResultDetail",
    "ValidationRule",
    "ValidationScore",
    "ValidationStatistics",
    "ValidationTarget",
    "ValidationTemplate",
]
