"""Snapshots, versions, and comparison ("VERSIONING").

A **version** is a cheap marker: counts and a timestamp, taken on every
sync if an installation wants one. A **snapshot** is the whole graph
serialised, which is expensive and taken deliberately. Keeping them
separate is why "when did the graph change shape?" does not require
storing a copy of it every time.

**A restore replaces, it does not merge.** Restoring a snapshot purges
the organization's nodes and rewrites them, because a merge would leave
behind everything created since the snapshot -- which is precisely the
data someone restoring is trying to remove. That makes restore
destructive, so it is scoped to one organization by parameter, records
what it removed, and never runs implicitly.

**Comparison works on keys, not payloads.** Two graphs differ in the
nodes and edges present and in which properties changed; diffing
serialised bytes would report a difference every time a timestamp moved.
"""

from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.exporter.formats import render
from app.graph.entities import (
    GraphNode,
    GraphRelationship,
    NodeInput,
    RelationshipInput,
    Subgraph,
)
from app.graph.repository import GraphRepository
from app.importer.formats import parse
from app.models.enums import GraphFormat, JobStatus
from app.models.graph_snapshot import GraphSnapshot
from app.models.graph_version import GraphVersion
from app.repositories.graph_snapshot import GraphSnapshotRepository
from app.repositories.graph_version import GraphVersionRepository

logger = get_logger("app.versioning.snapshots")

MAX_SNAPSHOT_NODES = 100_000
"""Nodes one snapshot may hold.

The payload is stored inline in PostgreSQL (see
:class:`~app.models.graph_snapshot.GraphSnapshot` for why), so the
ceiling is what keeps that choice honest rather than a promise that
quietly fails on a large estate.
"""


def status_of(record: GraphSnapshot) -> JobStatus:
    """A snapshot's status as a genuine enum member.

    ``status`` is annotated ``Mapped[JobStatus]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = record.status
    return value if isinstance(value, JobStatus) else JobStatus(value)


def format_of(record: GraphSnapshot) -> GraphFormat:
    """A snapshot's format as a genuine enum member."""
    value = record.snapshot_format
    return value if isinstance(value, GraphFormat) else GraphFormat(value)


@dataclass(slots=True)
class GraphDiff:
    """What changed between two graphs."""

    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    changed_nodes: list[dict[str, Any]] = field(default_factory=list)
    added_relationships: list[str] = field(default_factory=list)
    removed_relationships: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Whether the two graphs are identical."""
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_relationships
            or self.removed_relationships
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "added_nodes": self.added_nodes,
            "removed_nodes": self.removed_nodes,
            "changed_nodes": self.changed_nodes,
            "added_relationships": self.added_relationships,
            "removed_relationships": self.removed_relationships,
            "identical": self.is_empty,
            "total_changes": (
                len(self.added_nodes)
                + len(self.removed_nodes)
                + len(self.changed_nodes)
                + len(self.added_relationships)
                + len(self.removed_relationships)
            ),
        }


def compare(before: Subgraph, after: Subgraph) -> GraphDiff:
    """Diff two graphs by key ("Graph Comparison").

    Property changes are reported per node with the field names that
    moved, not the whole node: a diff that echoes both copies of
    everything is unreadable at the size a real graph reaches.
    """
    before_nodes = {node.key: node for node in before.nodes}
    after_nodes = {node.key: node for node in after.nodes}
    before_edges = {edge.relationship_key for edge in before.relationships}
    after_edges = {edge.relationship_key for edge in after.relationships}

    diff = GraphDiff(
        added_nodes=sorted(set(after_nodes) - set(before_nodes)),
        removed_nodes=sorted(set(before_nodes) - set(after_nodes)),
        added_relationships=sorted(after_edges - before_edges),
        removed_relationships=sorted(before_edges - after_edges),
    )

    for key in sorted(set(before_nodes) & set(after_nodes)):
        old, new = before_nodes[key], after_nodes[key]
        changed = [
            name
            for name, (was, now) in {
                "name": (old.name, new.name),
                "node_type": (old.node_type, new.node_type),
                "description": (old.description, new.description),
                "project_id": (old.project_id, new.project_id),
                "source": (old.source, new.source),
            }.items()
            if was != now
        ]
        if old.properties != new.properties:
            changed.append("properties")
        if changed:
            diff.changed_nodes.append({"key": key, "changed": changed})
    return diff


class SnapshotService:
    """Captures, restores, and compares graph snapshots."""

    def __init__(
        self,
        graph: GraphRepository,
        snapshots: GraphSnapshotRepository,
        versions: GraphVersionRepository,
        *,
        retention_days: int = 90,
        max_nodes: int = MAX_SNAPSHOT_NODES,
    ) -> None:
        self._graph = graph
        self._snapshots = snapshots
        self._versions = versions
        self._retention_days = retention_days
        self._max_nodes = max_nodes

    async def capture(
        self,
        organization_id: UUID,
        *,
        label: str,
        description: str | None = None,
        snapshot_format: GraphFormat = GraphFormat.JSON,
        actor_id: UUID | None = None,
    ) -> GraphSnapshot:
        """Serialise the whole organization graph into one row.

        Raises:
            ValidationError: If the graph exceeds the snapshot ceiling.
            DependencyError: If the graph is unreachable.
        """
        node_count = await self._graph.count_nodes(organization_id)
        if node_count > self._max_nodes:
            raise ValidationError(
                f"This graph has {node_count:,} nodes, above the "
                f"{self._max_nodes:,}-node snapshot ceiling."
            )

        record = await self._snapshots.create(
            GraphSnapshot(
                organization_id=organization_id,
                label=label,
                description=description,
                status=JobStatus.RUNNING,
                snapshot_format=snapshot_format,
                captured_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=self._retention_days),
                created_by=actor_id,
            )
        )
        try:
            subgraph = await self._collect(organization_id)
            payload, _content_type, _extension = render(subgraph, snapshot_format)
            compressed = gzip.compress(payload)
            record.payload = compressed
            record.size_bytes = len(compressed)
            record.checksum_sha256 = hashlib.sha256(compressed).hexdigest()
            record.node_count = len(subgraph.nodes)
            record.relationship_count = len(subgraph.relationships)
            record.status = JobStatus.SUCCEEDED
            record.details = {
                "uncompressed_bytes": len(payload),
                "compression_ratio": round(len(compressed) / max(1, len(payload)), 4),
            }
        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "A graph snapshot failed.",
                extra={"extra_fields": {"label": label, "error": str(exc)}},
            )
        return await self._snapshots.update(record)

    async def restore(
        self, organization_id: UUID, snapshot_id: UUID, *, actor_id: UUID | None = None
    ) -> dict[str, Any]:
        """Replace the organization's graph with a snapshot.

        **Destructive.** Every node in the organization is purged before
        the snapshot is written, because merging would leave behind
        exactly what someone restoring is trying to remove. Scoped to one
        organization by parameter and never triggered implicitly.

        Raises:
            NotFoundError: If the snapshot does not exist.
            ConflictError: If it did not complete, holds no payload, or
                its checksum no longer matches what was stored.
        """
        record = await self._snapshots.require_by_id(snapshot_id)
        if status_of(record) is not JobStatus.SUCCEEDED or record.payload is None:
            raise ConflictError(
                f"Snapshot {record.label!r} did not complete successfully and "
                "cannot be restored."
            )
        digest = hashlib.sha256(record.payload).hexdigest()
        if record.checksum_sha256 and digest != record.checksum_sha256:
            # Restoring a payload that does not match its recorded digest
            # would write corruption over a working graph.
            raise ConflictError(
                f"Snapshot {record.label!r} failed its checksum: stored "
                f"{record.checksum_sha256[:12]}..., computed {digest[:12]}.... "
                "It will not be restored."
            )

        parsed = parse(gzip.decompress(record.payload), format_of(record))
        removed = await self._graph.purge_organization(organization_id)
        nodes = await self._graph.upsert_nodes(organization_id, parsed.nodes)
        relationships = await self._graph.upsert_relationships(
            organization_id, parsed.relationships
        )
        logger.info(
            "Restored a graph snapshot.",
            extra={
                "extra_fields": {
                    "snapshot_id": str(snapshot_id),
                    "removed": removed,
                    "restored_nodes": nodes,
                }
            },
        )
        return {
            "snapshot_id": str(snapshot_id),
            "removed_nodes": removed,
            "restored_nodes": nodes,
            "restored_relationships": relationships,
            "rejected": parsed.rejected,
            "restored_by": str(actor_id) if actor_id else None,
        }

    async def create_version(
        self,
        organization_id: UUID,
        *,
        label: str,
        description: str | None = None,
        snapshot_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> GraphVersion:
        """Record a version marker with the graph's current shape."""
        return await self._versions.create(
            GraphVersion(
                organization_id=organization_id,
                sequence=await self._versions.next_sequence(organization_id),
                label=label,
                description=description,
                node_count=await self._graph.count_nodes(organization_id),
                relationship_count=await self._graph.count_relationships(organization_id),
                node_type_counts=await self._graph.type_counts(organization_id),
                relationship_type_counts=await self._graph.relationship_type_counts(
                    organization_id
                ),
                snapshot_id=snapshot_id,
                captured_at=datetime.now(UTC),
                captured_by=actor_id,
            )
        )

    async def compare_snapshots(
        self, organization_id: UUID, *, before_id: UUID, after_id: UUID
    ) -> GraphDiff:
        """Diff two stored snapshots.

        Raises:
            NotFoundError: If either snapshot does not exist.
            ConflictError: If either holds no payload.
        """
        before = await self._load(before_id)
        after = await self._load(after_id)
        del organization_id  # both snapshots carry their own scope
        return compare(before, after)

    async def compare_to_current(self, organization_id: UUID, snapshot_id: UUID) -> GraphDiff:
        """Diff a stored snapshot against the graph as it is now.

        The question an operator actually asks -- "what has changed since
        the snapshot?" -- rather than a comparison between two points in
        the past.
        """
        before = await self._load(snapshot_id)
        after = await self._collect(organization_id)
        return compare(before, after)

    async def list_snapshots(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[GraphSnapshot]:
        """Snapshots for one organization, newest first."""
        return await self._snapshots.list_for_org(organization_id, limit=limit)

    async def list_versions(self, organization_id: UUID, *, limit: int = 100) -> list[GraphVersion]:
        """Version markers for one organization, newest first."""
        return await self._versions.list_for_org(organization_id, limit=limit)

    async def sweep_expired(self, organization_id: UUID) -> int:
        """Delete snapshots past their retention; returns how many.

        Payloads are the largest rows this service writes, so an
        unswept retention window is the thing that fills the disk.
        """
        expired = await self._snapshots.list_expired(organization_id, moment=datetime.now(UTC))
        for record in expired:
            await self._snapshots.purge(record.id)
        if expired:
            logger.info(
                "Swept expired graph snapshots.",
                extra={"extra_fields": {"removed": len(expired)}},
            )
        return len(expired)

    async def _collect(self, organization_id: UUID) -> Subgraph:
        """Read the whole organization graph for serialisation."""
        nodes = await self._graph.list_nodes(organization_id, order_by="key", limit=self._max_nodes)
        relationships = await self._graph.list_relationships(organization_id, limit=self._max_nodes)
        return Subgraph(nodes=nodes, relationships=relationships)

    async def _load(self, snapshot_id: UUID) -> Subgraph:
        """Parse one stored snapshot back into a subgraph.

        Raises:
            NotFoundError: If the snapshot does not exist.
            ConflictError: If it holds no payload.
        """
        record = await self._snapshots.require_by_id(snapshot_id)
        if record.payload is None:
            raise ConflictError(f"Snapshot {record.label!r} holds no payload.")
        parsed = parse(gzip.decompress(record.payload), format_of(record))
        organization_id = str(record.organization_id)
        return Subgraph(
            nodes=[_as_graph_node(node, organization_id) for node in parsed.nodes],
            # Relationships are carried through too. Returning an empty
            # list would make every comparison report the entire edge set
            # as removed, which reads as a catastrophic change and is
            # purely an artefact of the loader.
            relationships=[_as_graph_relationship(edge) for edge in parsed.relationships],
        )


def _as_graph_node(node: NodeInput, organization_id: str) -> GraphNode:
    """Adapt a parsed ``NodeInput`` into the read-side node shape."""
    return GraphNode(
        key=node.key,
        node_type=str(node.node_type),
        name=node.name,
        organization_id=organization_id,
        description=node.description,
        project_id=node.project_id,
        source=node.source,
        properties=dict(node.properties),
    )


def _as_graph_relationship(edge: RelationshipInput) -> GraphRelationship:
    """Adapt a parsed ``RelationshipInput`` into the read-side edge shape."""
    return GraphRelationship(
        from_key=edge.from_key,
        to_key=edge.to_key,
        relationship_type=str(edge.relationship_type),
        weight=edge.weight,
        properties=dict(edge.properties),
    )


__all__ = [
    "MAX_SNAPSHOT_NODES",
    "GraphDiff",
    "SnapshotService",
    "compare",
    "format_of",
    "status_of",
]
