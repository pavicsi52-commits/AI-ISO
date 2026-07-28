"""SQLAlchemy models for the Dashboard Service.

Imported here so ``Base.metadata`` is fully populated before Alembic
autogenerates a migration -- a model that is never imported is silently
absent from the schema.
"""

from __future__ import annotations

from app.models.dashboard import Dashboard
from app.models.dashboard_audit import DashboardAudit
from app.models.dashboard_favorite import DashboardFavorite
from app.models.dashboard_filter import DashboardFilter
from app.models.dashboard_history import DashboardHistory
from app.models.dashboard_layout import DashboardLayout
from app.models.dashboard_permission import DashboardPermission
from app.models.dashboard_share import DashboardShare
from app.models.dashboard_statistics import DashboardStatistics
from app.models.dashboard_template import DashboardTemplate
from app.models.dashboard_theme import DashboardTheme
from app.models.dashboard_view import DashboardView
from app.models.dashboard_widget import DashboardWidget
from app.models.dashboard_widget_setting import DashboardWidgetSetting

__all__ = [
    "Dashboard",
    "DashboardAudit",
    "DashboardFavorite",
    "DashboardFilter",
    "DashboardHistory",
    "DashboardLayout",
    "DashboardPermission",
    "DashboardShare",
    "DashboardStatistics",
    "DashboardTemplate",
    "DashboardTheme",
    "DashboardView",
    "DashboardWidget",
    "DashboardWidgetSetting",
]
