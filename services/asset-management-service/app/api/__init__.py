"""REST API routers for the asset management service."""

from __future__ import annotations

from app.api.analytics import router as analytics_router
from app.api.asset_health import router as asset_health_router
from app.api.assignment import router as assignment_router
from app.api.compliance import router as compliance_router
from app.api.contract import router as contract_router
from app.api.cost import router as cost_router
from app.api.dependency import router as dependency_router
from app.api.health import router as health_router
from app.api.maintenance import router as maintenance_router
from app.api.managed_asset import router as managed_asset_router
from app.api.report import router as report_router
from app.api.risk import router as risk_router
from app.api.warranty import router as warranty_router

__all__ = [
    "analytics_router",
    "asset_health_router",
    "assignment_router",
    "compliance_router",
    "contract_router",
    "cost_router",
    "dependency_router",
    "health_router",
    "maintenance_router",
    "managed_asset_router",
    "report_router",
    "risk_router",
    "warranty_router",
]
