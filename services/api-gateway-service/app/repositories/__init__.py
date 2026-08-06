"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.apikey import ApiKeyPermissionRepository, ApiKeyRepository
from app.repositories.client import ApiClientRepository
from app.repositories.governance import (
    ApiAuditRepository,
    ApiReportRepository,
    ApiStatisticRepository,
)
from app.repositories.health import ApiServiceHealthRepository
from app.repositories.quota import ApiQuotaPolicyRepository
from app.repositories.ratelimit import ApiRateLimitPolicyRepository
from app.repositories.request import ApiRequestLogRepository, ApiResponseLogRepository
from app.repositories.route import ApiRouteRepository
from app.repositories.service import ApiServiceRepository
from app.repositories.transformation import ApiTransformationRuleRepository
from app.repositories.version import ApiVersionRepository

__all__ = [
    "ApiAuditRepository",
    "ApiClientRepository",
    "ApiKeyPermissionRepository",
    "ApiKeyRepository",
    "ApiQuotaPolicyRepository",
    "ApiRateLimitPolicyRepository",
    "ApiReportRepository",
    "ApiRequestLogRepository",
    "ApiResponseLogRepository",
    "ApiRouteRepository",
    "ApiServiceHealthRepository",
    "ApiServiceRepository",
    "ApiStatisticRepository",
    "ApiTransformationRuleRepository",
    "ApiVersionRepository",
]
