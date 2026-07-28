"""Repositories for the Dashboard Service."""

from __future__ import annotations

from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_audit import DashboardAuditRepository
from app.repositories.dashboard_favorite import DashboardFavoriteRepository
from app.repositories.dashboard_filter import DashboardFilterRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_permission import DashboardPermissionRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.repositories.dashboard_statistics import DashboardStatisticsRepository
from app.repositories.dashboard_template import DashboardTemplateRepository
from app.repositories.dashboard_theme import DashboardThemeRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.repositories.dashboard_widget_setting import DashboardWidgetSettingRepository

__all__ = [
    "DashboardAuditRepository",
    "DashboardFavoriteRepository",
    "DashboardFilterRepository",
    "DashboardHistoryRepository",
    "DashboardLayoutRepository",
    "DashboardPermissionRepository",
    "DashboardRepository",
    "DashboardShareRepository",
    "DashboardStatisticsRepository",
    "DashboardTemplateRepository",
    "DashboardThemeRepository",
    "DashboardViewRepository",
    "DashboardWidgetRepository",
    "DashboardWidgetSettingRepository",
]
