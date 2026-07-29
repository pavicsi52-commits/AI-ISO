"""Every ORM model, imported so ``Base.metadata`` is complete.

Alembic autogenerate and ``create_all`` both walk
:data:`shared_core.database.base.Base.metadata`, which is populated by
*import*. A model this package never imports is a table that never gets
a migration.

**Neo4j holds the graph; PostgreSQL holds everything about it.** None of
these tables stores a node or a relationship -- they store sync runs,
versions, snapshots, saved queries, change history, statistics,
per-node metadata, analyses, and audit. See ``app/config/settings.py``
for why the split is drawn there.
"""

from __future__ import annotations

from app.models.graph_audit import GraphAudit
from app.models.graph_change_history import GraphChangeHistory
from app.models.graph_export_job import GraphExportJob
from app.models.graph_import_job import GraphImportJob
from app.models.graph_metadata import GraphMetadata
from app.models.graph_query import GraphQuery
from app.models.graph_report import GraphReport
from app.models.graph_saved_query import GraphSavedQuery
from app.models.graph_snapshot import GraphSnapshot
from app.models.graph_statistics import GraphStatistics
from app.models.graph_sync_job import GraphSyncJob
from app.models.graph_version import GraphVersion

__all__ = [
    "GraphAudit",
    "GraphChangeHistory",
    "GraphExportJob",
    "GraphImportJob",
    "GraphMetadata",
    "GraphQuery",
    "GraphReport",
    "GraphSavedQuery",
    "GraphSnapshot",
    "GraphStatistics",
    "GraphSyncJob",
    "GraphVersion",
]
