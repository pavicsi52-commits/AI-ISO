"""The synchronization engine ("GRAPH SYNCHRONIZATION").

Pulls each source service's current state and merges it into the graph.

**Every write is a ``MERGE`` on ``(key, organization_id)``**, so a sync
is idempotent: running a full sync twice leaves the graph exactly as one
run did. That is what makes "just re-run it" a safe answer when someone
is unsure whether the graph is current, and it is why incremental and
full sync share the same write path rather than having separate ones.

**Incremental resumes from a cursor; full does not.** The cursor is the
newest ``updated_at`` the last run saw, stored on the job row. A source
that ignores the parameter returns everything, which still merges
correctly -- just slowly. A full sync deliberately passes no cursor,
which is the repair path when a source's change feed has lied.

**Deletes are the dangerous half, so they are conservative.** A node
absent from a full sync is removed only if it came from *that same
source* and is not pinned. Two guards, because both failure modes are
real: without the source check, syncing inventory would delete every
automation node; without the pin check, a node someone added by hand
disappears the first time a source that never knew about it runs.
Incremental syncs never delete at all -- absence from a change feed
means "unchanged", not "gone".

**One source failing does not fail the run.** Each is caught, recorded
against its own job row, and the loop continues. A source that fails
repeatedly is disabled after a configured count rather than retried
forever.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.clients.platform import PlatformSourceClient
from app.graph.entities import NodeInput, RelationshipInput
from app.graph.repository import GraphRepository
from app.models.enums import (
    ChangeAction,
    ConflictResolution,
    SyncMode,
    SyncSource,
    SyncStatus,
)
from app.models.graph_change_history import GraphChangeHistory
from app.models.graph_sync_job import GraphSyncJob
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.synchronization.mappers import SOURCE_PATHS, MappedBatch, map_rows

logger = get_logger("app.synchronization.engine")

MAX_PAGES = 200
"""Pages one source may yield in a single run.

A source stuck returning the same page forever would otherwise loop
until the process died. Hitting this marks the run ``PARTIAL``, which
says "there is more" rather than "this is everything".
"""


def status_of(job: GraphSyncJob) -> SyncStatus:
    """A job's status as a genuine enum member.

    ``status`` is annotated ``Mapped[SyncStatus]`` but stored in a
    ``String``, so a row loaded from Postgres yields a raw ``str``.
    Comparing that with ``is`` is ``False`` for every stored row.
    """
    value = job.status
    return value if isinstance(value, SyncStatus) else SyncStatus(value)


def source_of(job: GraphSyncJob) -> SyncSource:
    """A job's source as a genuine enum member."""
    value = job.source
    return value if isinstance(value, SyncSource) else SyncSource(value)


def mode_of(job: GraphSyncJob) -> SyncMode:
    """A job's mode as a genuine enum member."""
    value = job.mode
    return value if isinstance(value, SyncMode) else SyncMode(value)


def resolution_of(job: GraphSyncJob) -> ConflictResolution:
    """A job's conflict policy as a genuine enum member."""
    value = job.conflict_resolution
    return value if isinstance(value, ConflictResolution) else ConflictResolution(value)


@dataclass(slots=True)
class SyncOutcome:
    """What one source's synchronization produced."""

    source: SyncSource
    status: SyncStatus
    nodes: int = 0
    relationships: int = 0
    deleted: int = 0
    conflicts: int = 0
    rejections: list[dict[str, Any]] = field(default_factory=list)
    cursor: str | None = None
    error: str | None = None
    duration_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        """Whether the run completed without failing."""
        return self.status in (SyncStatus.SUCCEEDED, SyncStatus.PARTIAL)


class SynchronizationEngine:
    """Pulls source services into the graph."""

    def __init__(
        self,
        graph: GraphRepository,
        jobs: GraphSyncJobRepository,
        changes: GraphChangeHistoryRepository,
        metadata: GraphMetadataRepository,
        sources: PlatformSourceClient,
        *,
        batch_size: int = 500,
        max_failures: int = 5,
    ) -> None:
        self._graph = graph
        self._jobs = jobs
        self._changes = changes
        self._metadata = metadata
        self._sources = sources
        self._batch_size = batch_size
        self._max_failures = max_failures

    async def sync_source(
        self,
        organization_id: UUID,
        source: SyncSource,
        *,
        mode: SyncMode = SyncMode.INCREMENTAL,
        conflict_resolution: ConflictResolution = ConflictResolution.SOURCE_WINS,
        actor_id: UUID | None = None,
    ) -> GraphSyncJob:
        """Synchronize one source; returns its job row.

        Never raises for a source-side failure -- the failure is recorded
        on the job and returned, because a caller syncing ten sources
        needs the other nine to proceed.
        """
        previous = await self._jobs.latest_for_source(organization_id, source)
        if previous is not None and status_of(previous) is SyncStatus.DISABLED:
            logger.info(
                "Skipping a disabled sync source.",
                extra={"extra_fields": {"source": str(source)}},
            )
            return previous

        job = await self._jobs.create(
            GraphSyncJob(
                organization_id=organization_id,
                source=source,
                mode=mode,
                status=SyncStatus.RUNNING,
                conflict_resolution=conflict_resolution,
                started_at=datetime.now(UTC),
                created_by=actor_id,
                consecutive_failures=(previous.consecutive_failures if previous is not None else 0),
            )
        )

        cursor = previous.cursor if previous is not None and mode is SyncMode.INCREMENTAL else None
        outcome = await self._run(organization_id, source, mode=mode, cursor=cursor, job=job)

        job.status = outcome.status
        job.finished_at = datetime.now(UTC)
        job.duration_ms = outcome.duration_ms
        job.nodes_created = outcome.nodes
        job.relationships_created = outcome.relationships
        job.nodes_deleted = outcome.deleted
        job.conflicts_detected = outcome.conflicts
        job.error = outcome.error
        job.details = {"rejections": outcome.rejections[:20]}
        if outcome.succeeded:
            job.cursor = outcome.cursor or cursor
            job.consecutive_failures = 0
        else:
            job.consecutive_failures += 1
            if job.consecutive_failures >= self._max_failures:
                # Retrying a permanently broken source every five minutes
                # forever fills the log and buries the real problem.
                job.status = SyncStatus.DISABLED
                logger.warning(
                    "Disabling a sync source after repeated failures.",
                    extra={
                        "extra_fields": {
                            "source": str(source),
                            "failures": job.consecutive_failures,
                        }
                    },
                )
        return await self._jobs.update(job)

    async def sync_all(
        self,
        organization_id: UUID,
        *,
        sources: list[SyncSource] | None = None,
        mode: SyncMode = SyncMode.INCREMENTAL,
        actor_id: UUID | None = None,
    ) -> list[GraphSyncJob]:
        """Synchronize every source in turn.

        Sequentially, not concurrently. Each source writes to the same
        graph and the same session, and overlapping them would mean
        concurrent use of an ``AsyncSession`` -- not safe even for reads
        -- plus ``MERGE`` contention on shared nodes for no real gain,
        since the cost here is source-side I/O rather than this process.
        """
        selected = sources or list(SyncSource)
        jobs: list[GraphSyncJob] = []
        for source in selected:
            jobs.append(
                await self.sync_source(organization_id, source, mode=mode, actor_id=actor_id)
            )
        return jobs

    async def _run(
        self,
        organization_id: UUID,
        source: SyncSource,
        *,
        mode: SyncMode,
        cursor: str | None,
        job: GraphSyncJob,
    ) -> SyncOutcome:
        """Fetch, map, and merge one source."""
        started = time.monotonic()
        outcome = SyncOutcome(source=source, status=SyncStatus.SUCCEEDED)
        path = SOURCE_PATHS.get(source)
        if path is None:
            outcome.status = SyncStatus.FAILED
            outcome.error = f"No endpoint is configured for source {str(source)!r}."
            return outcome

        collected = MappedBatch()
        seen_keys: set[str] = set()
        newest_cursor = cursor
        offset = 0
        pages = 0

        try:
            while pages < MAX_PAGES:
                rows = await self._sources.fetch_page(
                    source,
                    path,
                    organization_id=str(organization_id),
                    since=cursor if mode is SyncMode.INCREMENTAL else None,
                    offset=offset,
                )
                if not rows:
                    break
                batch = map_rows(source, rows)
                collected.extend(batch)
                seen_keys.update(node.key for node in batch.nodes)
                newest_cursor = _newest(rows, newest_cursor)
                pages += 1
                offset += len(rows)
                if len(rows) < self._batch_size:
                    break
            else:
                outcome.status = SyncStatus.PARTIAL
                logger.warning(
                    "A sync source hit the page ceiling; the run is partial.",
                    extra={"extra_fields": {"source": str(source), "pages": pages}},
                )
        except Exception as exc:
            outcome.status = SyncStatus.FAILED
            outcome.error = str(exc)
            outcome.duration_ms = (time.monotonic() - started) * 1000
            logger.warning(
                "A sync source failed; the rest of the run continues.",
                extra={"extra_fields": {"source": str(source), "error": str(exc)}},
            )
            return outcome

        try:
            outcome.nodes = await self._merge_nodes(organization_id, collected.nodes, source)
            outcome.relationships = await self._merge_relationships(
                organization_id, collected.relationships
            )
            if mode is SyncMode.FULL:
                outcome.deleted = await self._remove_absent(
                    organization_id, source, seen_keys=seen_keys, job=job
                )
        except Exception as exc:
            outcome.status = SyncStatus.FAILED
            outcome.error = str(exc)
            logger.warning(
                "Merging a sync source into the graph failed.",
                extra={"extra_fields": {"source": str(source), "error": str(exc)}},
            )

        outcome.rejections = collected.rejections
        outcome.cursor = newest_cursor
        outcome.duration_ms = (time.monotonic() - started) * 1000
        return outcome

    async def _merge_nodes(
        self, organization_id: UUID, nodes: list[NodeInput], source: SyncSource
    ) -> int:
        """Merge mapped nodes and record what changed."""
        if not nodes:
            return 0
        written = await self._graph.upsert_nodes(organization_id, nodes, source=str(source))
        for node in nodes:
            await self._changes.create(
                GraphChangeHistory(
                    organization_id=organization_id,
                    action=ChangeAction.NODE_UPDATED,
                    node_key=node.key,
                    entity_type=str(node.node_type),
                    after={"name": node.name, "source": str(source)},
                    occurred_at=datetime.now(UTC),
                )
            )
        return written

    async def _merge_relationships(
        self, organization_id: UUID, relationships: list[RelationshipInput]
    ) -> int:
        """Merge mapped relationships.

        Edges whose endpoints are missing are skipped by the ``MATCH``
        rather than failing the batch. That is correct for a partial
        sync: an inventory run can legitimately reference an automation
        node that has not been synced yet, and the edge appears once it
        has.
        """
        if not relationships:
            return 0
        return await self._graph.upsert_relationships(organization_id, relationships)

    async def _remove_absent(
        self,
        organization_id: UUID,
        source: SyncSource,
        *,
        seen_keys: set[str],
        job: GraphSyncJob,
    ) -> int:
        """Delete nodes this source no longer reports.

        Scoped twice -- to this source, and excluding pinned nodes --
        because both unguarded forms are destructive in ways that look
        like a working sync until someone notices the graph is missing
        half of itself.
        """
        existing = await self._graph.list_nodes(organization_id, source=str(source), limit=10_000)
        pinned = {row.node_key for row in await self._metadata.list_pinned(organization_id)}
        removed = 0
        for node in existing:
            if node.key in seen_keys or node.key in pinned:
                continue
            if await self._graph.delete_node(organization_id, node.key):
                removed += 1
                await self._changes.create(
                    GraphChangeHistory(
                        organization_id=organization_id,
                        action=ChangeAction.NODE_DELETED,
                        node_key=node.key,
                        entity_type=node.node_type,
                        before={"name": node.name, "source": node.source},
                        sync_job_id=job.id,
                        occurred_at=datetime.now(UTC),
                    )
                )
        if removed:
            logger.info(
                "A full sync removed nodes the source no longer reports.",
                extra={"extra_fields": {"source": str(source), "removed": removed}},
            )
        return removed

    async def resolve_conflict(
        self,
        *,
        policy: ConflictResolution,
        source_value: Any,
        graph_value: Any,
        source_updated: datetime | None = None,
        graph_updated: datetime | None = None,
    ) -> Any:
        """Decide which side wins one disagreement ("Conflict Resolution").

        ``MANUAL`` keeps the graph's value and leaves the disagreement
        for a person: it is the policy for fields nobody wants a machine
        deciding, so silently taking either side would defeat the point
        of choosing it.
        """
        if policy is ConflictResolution.SOURCE_WINS:
            return source_value
        if policy is ConflictResolution.GRAPH_WINS:
            return graph_value
        if policy is ConflictResolution.NEWEST_WINS:
            if source_updated is None or graph_updated is None:
                # Without both timestamps "newest" is unanswerable, so it
                # falls back to the source rather than guessing.
                return source_value
            return source_value if source_updated >= graph_updated else graph_value
        return graph_value


def _newest(rows: list[dict[str, Any]], current: str | None) -> str | None:
    """The newest ``updated_at`` across *rows*, for the next cursor.

    String comparison, which is correct for ISO-8601 timestamps and
    avoids parsing every row of every page just to find a maximum.
    """
    newest = current
    for row in rows:
        stamp = row.get("updated_at") or row.get("modified_at") or row.get("created_at")
        if stamp and (newest is None or str(stamp) > newest):
            newest = str(stamp)
    return newest


__all__ = [
    "MAX_PAGES",
    "SyncOutcome",
    "SynchronizationEngine",
    "mode_of",
    "resolution_of",
    "source_of",
    "status_of",
]
