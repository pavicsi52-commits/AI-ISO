"""SQLAlchemy models for the Reporting Service.

Imported here so ``Base.metadata`` is fully populated before Alembic
autogenerates a migration -- a model that is never imported is silently
absent from the schema.
"""

from __future__ import annotations

from app.models.report_archive import ReportArchive
from app.models.report_audit import ReportAudit
from app.models.report_category import ReportCategoryRecord
from app.models.report_distribution import ReportDistribution
from app.models.report_execution import ReportExecution
from app.models.report_export import ReportExport
from app.models.report_favorite import ReportFavorite
from app.models.report_history import ReportHistory
from app.models.report_job import ReportJob
from app.models.report_parameter import ReportParameter
from app.models.report_recipient import ReportRecipient
from app.models.report_schedule import ReportSchedule
from app.models.report_statistics import ReportStatistics
from app.models.report_template import ReportTemplate

__all__ = [
    "ReportArchive",
    "ReportAudit",
    "ReportCategoryRecord",
    "ReportDistribution",
    "ReportExecution",
    "ReportExport",
    "ReportFavorite",
    "ReportHistory",
    "ReportJob",
    "ReportParameter",
    "ReportRecipient",
    "ReportSchedule",
    "ReportStatistics",
    "ReportTemplate",
]
