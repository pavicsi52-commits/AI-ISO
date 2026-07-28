"""Every alerting service repository."""

from __future__ import annotations

from app.repositories.alert_acknowledgement import AlertAcknowledgementRepository
from app.repositories.alert_audit import AlertAuditEntryRepository
from app.repositories.alert_condition import AlertConditionRepository
from app.repositories.alert_correlation import AlertCorrelationRepository
from app.repositories.alert_deduplication import AlertDeduplicationRepository
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.repositories.alert_notification import AlertNotificationRepository
from app.repositories.alert_oncall_schedule import AlertOnCallScheduleRepository
from app.repositories.alert_report import AlertReportRepository
from app.repositories.alert_route import AlertRouteRepository
from app.repositories.alert_rule import AlertRuleRepository
from app.repositories.alert_statistics import AlertStatisticsRepository
from app.repositories.alert_suppression import AlertSuppressionRepository

__all__ = [
    "AlertAcknowledgementRepository",
    "AlertAuditEntryRepository",
    "AlertConditionRepository",
    "AlertCorrelationRepository",
    "AlertDeduplicationRepository",
    "AlertEscalationPolicyRepository",
    "AlertHistoryRepository",
    "AlertInstanceRepository",
    "AlertMaintenanceWindowRepository",
    "AlertNotificationRepository",
    "AlertOnCallScheduleRepository",
    "AlertReportRepository",
    "AlertRouteRepository",
    "AlertRuleRepository",
    "AlertStatisticsRepository",
    "AlertSuppressionRepository",
]
