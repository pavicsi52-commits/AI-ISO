"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id`` -- two same-named
methods of different arity on one class make an unscoped call look
correct, which is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.connector import (
    ConnectorCategoryRepository,
    ConnectorRepository,
    ConnectorVersionRepository,
)
from app.repositories.credential import ConnectorConnectionRepository, ConnectorCredentialRepository
from app.repositories.event import ConnectorEventRepository
from app.repositories.flow import ConnectorFlowRepository
from app.repositories.governance import (
    ConnectorAuditRepository,
    ConnectorReportRepository,
    ConnectorStatisticRepository,
)
from app.repositories.health import ConnectorHealthRepository
from app.repositories.marketplace import ConnectorMarketplaceRepository
from app.repositories.sync import ConnectorSyncJobRepository
from app.repositories.transformation import ConnectorTransformationRepository

__all__ = [
    "ConnectorAuditRepository",
    "ConnectorCategoryRepository",
    "ConnectorConnectionRepository",
    "ConnectorCredentialRepository",
    "ConnectorEventRepository",
    "ConnectorFlowRepository",
    "ConnectorHealthRepository",
    "ConnectorMarketplaceRepository",
    "ConnectorReportRepository",
    "ConnectorRepository",
    "ConnectorStatisticRepository",
    "ConnectorSyncJobRepository",
    "ConnectorTransformationRepository",
    "ConnectorVersionRepository",
]
