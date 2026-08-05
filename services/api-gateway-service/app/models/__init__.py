"""Every table this service owns.

Imported as a package by Alembic's ``env.py``, which is what registers
each model with ``Base.metadata`` before autogenerate runs. A model not
re-exported here is a table the migration will not know about.
"""

from __future__ import annotations

from app.models.apikey import ApiKey, ApiKeyPermission
from app.models.client import ApiClient
from app.models.governance import ApiAudit, ApiReport, ApiStatistic
from app.models.health import ApiServiceHealth
from app.models.quota import ApiQuotaPolicy
from app.models.ratelimit import ApiRateLimitPolicy
from app.models.request import ApiRequestLog, ApiResponseLog
from app.models.route import ApiRoute
from app.models.service import ApiService
from app.models.transformation import ApiTransformationRule
from app.models.version import ApiVersion

__all__ = [
    "ApiAudit",
    "ApiClient",
    "ApiKey",
    "ApiKeyPermission",
    "ApiQuotaPolicy",
    "ApiRateLimitPolicy",
    "ApiReport",
    "ApiRequestLog",
    "ApiResponseLog",
    "ApiRoute",
    "ApiService",
    "ApiServiceHealth",
    "ApiStatistic",
    "ApiTransformationRule",
    "ApiVersion",
]
