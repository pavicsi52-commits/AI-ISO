"""Repositories for every PostgreSQL table this service owns.

Each wraps :class:`shared_core.database.repository.BaseRepository`, so
soft delete, optimistic locking, and tenant scoping all behave the same
way they do in every other AI-IOS service.

Nothing here touches Neo4j -- the graph is reached through
:mod:`app.graph.client`, which is a different kind of store with a
different session model and deserves its own boundary.
"""

from __future__ import annotations

from app.repositories.graph_audit import GraphAuditRepository
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_export_job import GraphExportJobRepository
from app.repositories.graph_import_job import GraphImportJobRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_query import GraphQueryRepository
from app.repositories.graph_report import GraphReportRepository
from app.repositories.graph_saved_query import GraphSavedQueryRepository
from app.repositories.graph_snapshot import GraphSnapshotRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.repositories.graph_version import GraphVersionRepository

__all__ = [
    "GraphAuditRepository",
    "GraphChangeHistoryRepository",
    "GraphExportJobRepository",
    "GraphImportJobRepository",
    "GraphMetadataRepository",
    "GraphQueryRepository",
    "GraphReportRepository",
    "GraphSavedQueryRepository",
    "GraphSnapshotRepository",
    "GraphStatisticsRepository",
    "GraphSyncJobRepository",
    "GraphVersionRepository",
]
