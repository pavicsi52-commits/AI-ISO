"""Import and export as a service ("IMPORT / EXPORT").

Wraps the pure parsers and writers with the job rows, notifications, and
audit an unattended bulk operation needs.

**A dry run parses everything and writes nothing.** That is not a
courtesy: an import is the one operation here that can corrupt a graph
wholesale, and finding out a file is malformed *after* it has half
landed is the failure mode worth spending an endpoint to avoid.

**Rejections are reported, never swallowed.** A job that says "imported
900" when the file held 1,000 rows has told you nothing about the
hundred that vanished, so every rejection is counted and the first
twenty are stored with their reasons.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.exporter.formats import FILE_EXTENSIONS, render
from app.graph.repository import GraphRepository
from app.importer.formats import parse
from app.models.enums import GraphFormat, JobStatus, NodeType
from app.models.graph_export_job import GraphExportJob
from app.models.graph_import_job import GraphImportJob
from app.notifications.graph_notifications import GraphNotificationService
from app.repositories.graph_export_job import GraphExportJobRepository
from app.repositories.graph_import_job import GraphImportJobRepository

logger = get_logger("app.services.graph_io")

_MAX_STORED_REJECTIONS = 20


def import_status_of(job: GraphImportJob) -> JobStatus:
    """An import job's status as a genuine enum member."""
    value = job.status
    return value if isinstance(value, JobStatus) else JobStatus(value)


def import_format_of(job: GraphImportJob) -> GraphFormat:
    """An import job's format as a genuine enum member."""
    value = job.import_format
    return value if isinstance(value, GraphFormat) else GraphFormat(value)


def export_format_of(job: GraphExportJob) -> GraphFormat:
    """An export job's format as a genuine enum member."""
    value = job.export_format
    return value if isinstance(value, GraphFormat) else GraphFormat(value)


class GraphIoService:
    """Runs bulk imports and exports."""

    def __init__(
        self,
        graph: GraphRepository,
        imports: GraphImportJobRepository,
        exports: GraphExportJobRepository,
        notifications: GraphNotificationService,
        *,
        max_import_nodes: int = 50_000,
        max_export_nodes: int = 50_000,
    ) -> None:
        self._graph = graph
        self._imports = imports
        self._exports = exports
        self._notifications = notifications
        self._max_import = max_import_nodes
        self._max_export = max_export_nodes

    async def import_graph(
        self,
        organization_id: UUID,
        *,
        payload: bytes,
        filename: str,
        graph_format: GraphFormat,
        dry_run: bool = False,
        actor_id: UUID | None = None,
    ) -> GraphImportJob:
        """Parse a payload and, unless *dry_run*, merge it into the graph.

        Never raises for a malformed payload -- the failure is recorded
        on the job and returned, because a caller uploading a file needs
        to be told what was wrong with it rather than handed a stack
        trace.
        """
        job = await self._imports.create(
            GraphImportJob(
                organization_id=organization_id,
                filename=filename,
                import_format=graph_format,
                status=JobStatus.RUNNING,
                dry_run=dry_run,
                started_at=datetime.now(UTC),
                created_by=actor_id,
            )
        )
        started = time.monotonic()
        try:
            parsed = parse(payload, graph_format)
            if len(parsed.nodes) > self._max_import:
                raise ValueError(
                    f"This payload holds {len(parsed.nodes):,} nodes, above the "
                    f"{self._max_import:,}-node import ceiling."
                )

            job.rejected = parsed.rejected
            job.rejections = parsed.rejections[:_MAX_STORED_REJECTIONS]
            if dry_run:
                # Counted as what *would* land, so a dry run and the real
                # run report the same numbers for the same file.
                job.nodes_imported = len(parsed.nodes)
                job.relationships_imported = len(parsed.relationships)
            else:
                job.nodes_imported = await self._graph.upsert_nodes(
                    organization_id, parsed.nodes, source="import"
                )
                job.relationships_imported = await self._graph.upsert_relationships(
                    organization_id, parsed.relationships
                )
            job.status = JobStatus.SUCCEEDED
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            logger.warning(
                "A graph import failed.",
                extra={"extra_fields": {"filename": filename, "error": str(exc)}},
            )
            if actor_id is not None:
                await self._notifications.send_import_failed(
                    str(actor_id), filename=filename, reason=str(exc)
                )

        job.finished_at = datetime.now(UTC)
        job.duration_ms = (time.monotonic() - started) * 1000
        return await self._imports.update(job)

    async def export_graph(
        self,
        organization_id: UUID,
        *,
        graph_format: GraphFormat,
        node_types: list[NodeType] | None = None,
        project_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> GraphExportJob:
        """Render the organization's graph into one downloadable payload."""
        # The real extension comes back from render() below; this is
        # only the placeholder the job row carries until it does, so a
        # failed export still has a plausible filename to report.
        job = await self._exports.create(
            GraphExportJob(
                organization_id=organization_id,
                export_format=graph_format,
                status=JobStatus.RUNNING,
                filename=f"graph-export.{FILE_EXTENSIONS[graph_format]}",
                filters={
                    "node_types": [str(one) for one in node_types or []],
                    "project_id": project_id,
                },
                started_at=datetime.now(UTC),
                created_by=actor_id,
            )
        )
        started = time.monotonic()
        try:
            # collect_graph, not two raw list calls: the export ceiling is
            # 50,000 nodes and a single read returns at most 10,000, so
            # asking directly failed every export in every format with
            # "Limit must be between 1 and 10000, got 50000". It also
            # drops edges whose endpoints were filtered out, which would
            # otherwise re-import as rejections from a file this service
            # had just written.
            subgraph = await self._graph.collect_graph(
                organization_id,
                node_types=node_types,
                project_id=project_id,
                max_nodes=self._max_export,
            )
            nodes, relationships = subgraph.nodes, subgraph.relationships

            payload, content_type, rendered_extension = render(subgraph, graph_format)
            job.filename = f"graph-export.{rendered_extension}"
            job.content_type = content_type
            job.payload = payload
            job.size_bytes = len(payload)
            job.checksum_sha256 = hashlib.sha256(payload).hexdigest()
            job.node_count = len(nodes)
            job.relationship_count = len(relationships)
            job.status = JobStatus.SUCCEEDED
            if actor_id is not None:
                await self._notifications.send_export_completed(
                    str(actor_id), filename=job.filename, node_count=len(nodes)
                )
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            logger.warning(
                "A graph export failed.",
                extra={"extra_fields": {"format": str(graph_format), "error": str(exc)}},
            )

        job.finished_at = datetime.now(UTC)
        job.duration_ms = (time.monotonic() - started) * 1000
        return await self._exports.update(job)

    async def list_imports(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[GraphImportJob]:
        """Import runs, newest first."""
        return await self._imports.list_for_org(organization_id, limit=limit)

    async def list_exports(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[GraphExportJob]:
        """Export runs, newest first."""
        return await self._exports.list_for_org(organization_id, limit=limit)

    async def get_export(self, export_id: UUID) -> GraphExportJob:
        """One export job, payload included, for download.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._exports.require_by_id(export_id)

    def verify(self, job: GraphExportJob) -> dict[str, Any]:
        """Check a stored export against its recorded digest.

        A download that silently serves corrupted bytes is worse than one
        that refuses, and the digest is the only thing that can tell the
        difference.
        """
        if job.payload is None:
            return {"valid": False, "reason": "the export holds no payload"}
        digest = hashlib.sha256(job.payload).hexdigest()
        return {
            "valid": digest == job.checksum_sha256,
            "expected": job.checksum_sha256,
            "computed": digest,
            "size_bytes": len(job.payload),
        }


__all__ = [
    "GraphIoService",
    "export_format_of",
    "import_format_of",
    "import_status_of",
]
