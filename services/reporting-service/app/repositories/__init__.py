"""Repositories for the Reporting Service."""

from __future__ import annotations

from app.repositories.report_archive import ReportArchiveRepository
from app.repositories.report_audit import ReportAuditRepository
from app.repositories.report_category import ReportCategoryRepository
from app.repositories.report_distribution import ReportDistributionRepository
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_favorite import ReportFavoriteRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_parameter import ReportParameterRepository
from app.repositories.report_recipient import ReportRecipientRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.repositories.report_statistics import ReportStatisticsRepository
from app.repositories.report_template import ReportTemplateRepository

__all__ = [
    "ReportArchiveRepository",
    "ReportAuditRepository",
    "ReportCategoryRepository",
    "ReportDistributionRepository",
    "ReportExecutionRepository",
    "ReportExportRepository",
    "ReportFavoriteRepository",
    "ReportHistoryRepository",
    "ReportJobRepository",
    "ReportParameterRepository",
    "ReportRecipientRepository",
    "ReportScheduleRepository",
    "ReportStatisticsRepository",
    "ReportTemplateRepository",
]
