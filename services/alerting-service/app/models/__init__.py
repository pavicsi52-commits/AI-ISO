"""Every alerting service entity model.

Importing this package registers all sixteen tables with
:data:`shared_core.database.base.Base.metadata`, which is what
``alembic/env.py`` targets for autogenerate support.
"""

from __future__ import annotations

from app.models.alert_acknowledgement import AlertAcknowledgement
from app.models.alert_audit import AlertAuditEntry
from app.models.alert_condition import AlertCondition
from app.models.alert_correlation import AlertCorrelation
from app.models.alert_deduplication import AlertDeduplication
from app.models.alert_escalation import AlertEscalationPolicy
from app.models.alert_history import AlertHistory
from app.models.alert_instance import AlertInstance
from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.alert_notification import AlertNotification
from app.models.alert_oncall_schedule import AlertOnCallSchedule
from app.models.alert_report import AlertReport
from app.models.alert_route import AlertRoute
from app.models.alert_rule import AlertRule
from app.models.alert_statistics import AlertStatistics
from app.models.alert_suppression import AlertSuppression

__all__ = [
    "AlertAcknowledgement",
    "AlertAuditEntry",
    "AlertCondition",
    "AlertCorrelation",
    "AlertDeduplication",
    "AlertEscalationPolicy",
    "AlertHistory",
    "AlertInstance",
    "AlertMaintenanceWindow",
    "AlertNotification",
    "AlertOnCallSchedule",
    "AlertReport",
    "AlertRoute",
    "AlertRule",
    "AlertStatistics",
    "AlertSuppression",
]
