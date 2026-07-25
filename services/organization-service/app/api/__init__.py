"""REST API routers for the organization service."""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.department import org_router as department_org_router
from app.api.department import router as department_router
from app.api.health import router as health_router
from app.api.invitation import org_router as invitation_org_router
from app.api.invitation import router as invitation_router
from app.api.organization import router as organization_router
from app.api.organization_branding import router as organization_branding_router
from app.api.organization_license import router as organization_license_router
from app.api.organization_quota import router as organization_quota_router
from app.api.organization_settings import router as organization_settings_router
from app.api.team import org_router as team_org_router
from app.api.team import router as team_router

__all__ = [
    "analytics_router",
    "department_org_router",
    "department_router",
    "health_router",
    "invitation_org_router",
    "invitation_router",
    "organization_branding_router",
    "organization_license_router",
    "organization_quota_router",
    "organization_router",
    "organization_settings_router",
    "team_org_router",
    "team_router",
]
