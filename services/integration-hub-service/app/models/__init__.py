"""Every table this service owns -- imported here so Alembic autogenerate
and ``shared_core.database.base.Base.metadata`` see all of them."""

from __future__ import annotations

from app.models.connector import Connector, ConnectorCategoryEntry, ConnectorVersion
from app.models.credential import ConnectorConnection, ConnectorCredential
from app.models.event import ConnectorEvent
from app.models.flow import ConnectorFlow
from app.models.governance import ConnectorAudit, ConnectorReport, ConnectorStatistic
from app.models.health import ConnectorHealth
from app.models.marketplace import ConnectorMarketplaceEntry
from app.models.sync import ConnectorSyncJob
from app.models.transformation import ConnectorTransformation

__all__ = [
    "Connector",
    "ConnectorAudit",
    "ConnectorCategoryEntry",
    "ConnectorConnection",
    "ConnectorCredential",
    "ConnectorEvent",
    "ConnectorFlow",
    "ConnectorHealth",
    "ConnectorMarketplaceEntry",
    "ConnectorReport",
    "ConnectorStatistic",
    "ConnectorSyncJob",
    "ConnectorTransformation",
    "ConnectorVersion",
]
