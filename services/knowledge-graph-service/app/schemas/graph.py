"""Request and response shapes for the knowledge graph API.

These are the HTTP boundary. They deliberately do **not** re-implement
the validation that lives in :mod:`app.cypher.builder`,
:mod:`app.cypher.guard`, and :mod:`app.graph.entities` -- a node arrives
shaped, and whether its label is one this service will write into a
Cypher statement is decided by the module that owns that question.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AnalyticsAlgorithm,
    AuditAction,
    AuditOutcome,
    ConflictResolution,
    GraphFormat,
    JobStatus,
    LifecycleState,
    NodeType,
    QueryKind,
    RelationshipType,
    SyncMode,
    SyncSource,
    SyncStatus,
    TraversalDirection,
    TwinType,
)

# ---- nodes -----------------------------------------------------------


class NodeCreateRequest(BaseModel):
    """Create or update one node."""

    key: str = Field(min_length=1, max_length=255)
    node_type: NodeType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    project_id: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


class NodeResponse(BaseModel):
    """One node as returned."""

    key: str
    node_type: str
    name: str
    description: str | None = None
    organization_id: str
    project_id: str | None = None
    source: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class RelationshipCreateRequest(BaseModel):
    """Create or update one relationship."""

    from_key: str = Field(min_length=1, max_length=255)
    to_key: str = Field(min_length=1, max_length=255)
    relationship_type: RelationshipType
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationshipResponse(BaseModel):
    """One relationship as returned."""

    relationship_key: str
    from_key: str
    to_key: str
    relationship_type: str
    weight: float
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class SubgraphResponse(BaseModel):
    """A set of nodes and the relationships between them."""

    root_key: str | None = None
    nodes: list[NodeResponse] = Field(default_factory=list)
    relationships: list[RelationshipResponse] = Field(default_factory=list)
    node_count: int = 0
    relationship_count: int = 0
    truncated: bool = False


# ---- queries ---------------------------------------------------------


class GraphQueryRequest(BaseModel):
    """Run one query from the built-in catalogue."""

    kind: QueryKind
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=5_000)


class CypherRequest(BaseModel):
    """Run caller-authored Cypher, read-only.

    ``parameters`` is not optional in practice: the guard refuses any
    statement containing a bare literal, so anything a caller wants to
    compare against has to arrive here.
    """

    cypher: str = Field(min_length=1, max_length=10_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=5_000)


class SavedQueryRequest(BaseModel):
    """Store a reusable, parameterised query."""

    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    cypher: str = Field(min_length=1, max_length=10_000)
    description: str | None = Field(default=None, max_length=2_000)
    kind: QueryKind = QueryKind.CUSTOM_CYPHER
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    default_parameters: dict[str, Any] = Field(default_factory=dict)


class SavedQueryRunRequest(BaseModel):
    """Run a stored query with the caller's parameters bound.

    A declared model rather than a bare ``dict`` parameter on the route.
    FastAPI binds an undeclared ``dict`` to the *whole* body, so
    ``{"parameters": {...}}`` arrived as a parameter map containing one
    key called "parameters" -- and every parameterised saved query
    answered 400 saying the parameter it had just been given was
    missing. It also gives the endpoint a documented body instead of an
    untyped object in the OpenAPI schema.
    """

    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=200, ge=1, le=5_000)


class SavedQueryResponse(BaseModel):
    """One stored query."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    kind: QueryKind
    cypher: str
    parameter_schema: dict[str, Any]
    default_parameters: dict[str, Any]
    is_system: bool
    execution_count: int


class QueryResultResponse(BaseModel):
    """The result of one query execution."""

    kind: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0.0
    truncated: bool = False


# ---- analysis --------------------------------------------------------


class AnalysisResponse(BaseModel):
    """One dependency, impact, or blast-radius analysis."""

    root: NodeResponse
    direction: str
    depth: int
    affected: list[dict[str, Any]] = Field(default_factory=list)
    affected_count: int = 0
    affected_by_type: dict[str, int] = Field(default_factory=dict)
    relationships: list[RelationshipResponse] = Field(default_factory=list)
    risk_score: float = 0.0
    severity: str = "low"
    truncated: bool = False


class AnalyticsRequest(BaseModel):
    """Run one graph algorithm."""

    algorithm: AnalyticsAlgorithm
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalyticsResponse(BaseModel):
    """The result of one algorithm."""

    algorithm: str
    values: dict[str, Any] = Field(default_factory=dict)
    ranked: list[dict[str, Any]] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    duration_ms: float = 0.0


# ---- digital twin ----------------------------------------------------


class TwinStateRequest(BaseModel):
    """Record twin state for one node."""

    lifecycle_state: LifecycleState | None = None
    health_status: str | None = Field(default=None, max_length=16)
    criticality: float | None = Field(default=None, ge=0.0, le=1.0)
    owner_team: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    attributes: dict[str, Any] | None = None
    is_pinned: bool | None = None


class TwinResponse(BaseModel):
    """One digital twin."""

    node: NodeResponse
    twin_type: str | None
    lifecycle_state: str
    health: str
    is_operational: bool
    criticality: float
    owner_team: str | None
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    components: list[NodeResponse] = Field(default_factory=list)
    component_count: int = 0
    dependencies: list[NodeResponse] = Field(default_factory=list)
    dependents: list[NodeResponse] = Field(default_factory=list)
    component_health: dict[str, str] = Field(default_factory=dict)
    synchronised_at: str


class TwinSummary(BaseModel):
    """One tracked twin, from its metadata row."""

    model_config = ConfigDict(from_attributes=True)

    node_key: str
    node_type: str
    display_name: str | None
    twin_type: TwinType | None
    lifecycle_state: LifecycleState
    health_status: str | None
    criticality: float
    owner_team: str | None
    tags: list[str]
    is_pinned: bool


# ---- synchronization -------------------------------------------------


class SyncRequest(BaseModel):
    """Trigger synchronization."""

    sources: list[SyncSource] | None = None
    mode: SyncMode = SyncMode.INCREMENTAL
    conflict_resolution: ConflictResolution = ConflictResolution.SOURCE_WINS
    version_label: str | None = Field(default=None, max_length=255)


class SyncJobResponse(BaseModel):
    """One synchronization run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: SyncSource
    mode: SyncMode
    status: SyncStatus
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: float | None
    nodes_created: int
    nodes_updated: int
    nodes_deleted: int
    relationships_created: int
    consecutive_failures: int
    error: str | None


# ---- import / export -------------------------------------------------


class ImportRequest(BaseModel):
    """Import a graph payload.

    The payload arrives base64-encoded in ``content`` so one JSON body
    carries every format -- GraphML and Cypher are text, but a CSV can
    legitimately hold bytes that are not valid UTF-8 in a JSON string.
    """

    filename: str = Field(min_length=1, max_length=512)
    graph_format: GraphFormat
    content: str = Field(min_length=1)
    dry_run: bool = False


class ImportJobResponse(BaseModel):
    """One import run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    import_format: GraphFormat
    status: JobStatus
    dry_run: bool
    nodes_imported: int
    relationships_imported: int
    rejected: int
    rejections: list[dict[str, Any]]
    duration_ms: float | None
    error: str | None


class ExportRequest(BaseModel):
    """Export the organization's graph."""

    graph_format: GraphFormat = GraphFormat.JSON
    node_types: list[NodeType] | None = None
    project_id: str | None = Field(default=None, max_length=64)


class ExportJobResponse(BaseModel):
    """One export run, without its payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    export_format: GraphFormat
    status: JobStatus
    filename: str
    content_type: str
    node_count: int
    relationship_count: int
    size_bytes: int
    checksum_sha256: str | None
    duration_ms: float | None
    error: str | None


# ---- snapshots and versions ------------------------------------------


class SnapshotRequest(BaseModel):
    """Capture a snapshot."""

    label: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    snapshot_format: GraphFormat = GraphFormat.JSON


class SnapshotResponse(BaseModel):
    """One snapshot, without its payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    description: str | None
    status: JobStatus
    snapshot_format: GraphFormat
    node_count: int
    relationship_count: int
    size_bytes: int
    checksum_sha256: str | None
    captured_at: datetime
    expires_at: datetime | None
    error: str | None


class VersionResponse(BaseModel):
    """One version marker."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    label: str
    description: str | None
    node_count: int
    relationship_count: int
    snapshot_id: UUID | None
    captured_at: datetime


class DiffResponse(BaseModel):
    """What changed between two graphs."""

    added_nodes: list[str] = Field(default_factory=list)
    removed_nodes: list[str] = Field(default_factory=list)
    changed_nodes: list[dict[str, Any]] = Field(default_factory=list)
    added_relationships: list[str] = Field(default_factory=list)
    removed_relationships: list[str] = Field(default_factory=list)
    identical: bool = True
    total_changes: int = 0


# ---- search, statistics, audit ---------------------------------------


class SearchResponse(BaseModel):
    """One page of search results."""

    hits: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False
    truncated: bool = False


class StatisticsResponse(BaseModel):
    """An organization's graph statistics."""

    model_config = ConfigDict(from_attributes=True)

    node_count: int
    relationship_count: int
    node_type_counts: dict[str, Any]
    relationship_type_counts: dict[str, Any]
    orphan_count: int
    average_degree: float
    max_degree: int
    density: float
    connected_components: int
    critical_assets: list[dict[str, Any]]
    twin_counts: dict[str, Any]
    sync_health: dict[str, Any]
    computed_at: datetime


class AuditEntryResponse(BaseModel):
    """One audited graph action."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: AuditAction
    outcome: AuditOutcome
    entity_type: str
    entity_key: str | None
    actor_id: UUID | None
    reason: str | None
    context: dict[str, Any]
    occurred_at: datetime


class ChangeEntryResponse(BaseModel):
    """One recorded graph change."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    node_key: str | None
    relationship_key: str | None
    entity_type: str
    before: dict[str, Any]
    after: dict[str, Any]
    actor_id: UUID | None
    occurred_at: datetime


class TopologyQueryParams(BaseModel):
    """Shared traversal parameters."""

    depth: int = Field(default=2, ge=1, le=15)
    direction: TraversalDirection = TraversalDirection.BOTH
    relationship_types: list[RelationshipType] | None = None
    node_types: list[NodeType] | None = None


__all__ = [
    "AnalysisResponse",
    "AnalyticsRequest",
    "AnalyticsResponse",
    "AuditEntryResponse",
    "ChangeEntryResponse",
    "CypherRequest",
    "DiffResponse",
    "ExportJobResponse",
    "ExportRequest",
    "GraphQueryRequest",
    "ImportJobResponse",
    "ImportRequest",
    "NodeCreateRequest",
    "NodeResponse",
    "QueryResultResponse",
    "RelationshipCreateRequest",
    "RelationshipResponse",
    "SavedQueryRequest",
    "SavedQueryResponse",
    "SavedQueryRunRequest",
    "SearchResponse",
    "SnapshotRequest",
    "SnapshotResponse",
    "StatisticsResponse",
    "SubgraphResponse",
    "SyncJobResponse",
    "SyncRequest",
    "TopologyQueryParams",
    "TwinResponse",
    "TwinStateRequest",
    "TwinSummary",
    "VersionResponse",
]
