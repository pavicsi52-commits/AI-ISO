"""Node, relationship, topology, and analysis endpoints.

Paths follow docs/049 "REST APIs" exactly. No ``/api/v1`` prefix -- the
gateway owns versioning, the convention every AI-IOS service follows.

**Route order matters.** docs/049 specifies both ``/graph/nodes/{id}``
and literal collections like ``/graph/topology``. FastAPI matches in
declaration order, so literal paths are declared before any
``{node_key}`` route -- otherwise ``/graph/dependencies`` parses as a
node whose key is the word "dependencies".

**``{id}`` in the spec is the node's business key**, not a UUID. Neo4j
internal ids are reused after deletion and are not stable across a
restore, so nothing outside :mod:`app.graph.repository` ever sees one.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.enums.health_status import HealthStatus
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AnalyticsSvc,
    AuditSvc,
    CurrentUserId,
    GraphSvc,
    TwinSvc,
)
from app.graph.entities import NodeInput, RelationshipInput
from app.models.enums import (
    AuditAction,
    NodeType,
    RelationshipType,
    TraversalDirection,
)
from app.schemas.graph import (
    AnalysisResponse,
    NodeCreateRequest,
    NodeResponse,
    RelationshipCreateRequest,
    RelationshipResponse,
    SubgraphResponse,
    TwinResponse,
    TwinStateRequest,
    TwinSummary,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/graph", tags=["Graph"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _subgraph(payload: dict[str, object]) -> SubgraphResponse:
    """Adapt a subgraph dict into its response shape."""
    return SubgraphResponse.model_validate(payload)


# ---- nodes -----------------------------------------------------------


@router.get(
    "/nodes",
    response_model=SuccessResponse[list[NodeResponse]],
    summary="List graph nodes",
)
async def list_nodes(
    organization_id: UUID,
    graph: GraphSvc,
    caller: CurrentUserId,
    node_types: Annotated[list[NodeType] | None, Query()] = None,
    project_id: str | None = None,
    source: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[NodeResponse]]:
    """Return nodes for one organization, filtered and paginated."""
    del caller  # authentication is the requirement; the graph is org-scoped
    nodes = await graph.list_nodes(
        organization_id,
        node_types=node_types,
        project_id=project_id,
        source=source,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        message=f"Found {len(nodes)} nodes.",
        data=[NodeResponse.model_validate(node.as_dict()) for node in nodes],
        meta=_meta(),
    )


@router.post(
    "/nodes",
    response_model=SuccessResponse[NodeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a node",
)
async def create_node(
    organization_id: UUID,
    body: NodeCreateRequest,
    graph: GraphSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[NodeResponse]:
    """Create or update one node.

    Idempotent: writing the same key twice updates rather than
    duplicates, which is what makes synchronization safe to re-run.
    """
    node = await graph.create_node(
        organization_id,
        NodeInput(
            key=body.key,
            node_type=body.node_type,
            name=body.name,
            description=body.description,
            project_id=body.project_id,
            source=body.source,
            properties=body.properties,
        ),
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.NODE_CHANGED,
        entity_type="node",
        entity_key=node.key,
        actor_id=caller,
        context={"node_type": node.node_type},
    )
    return SuccessResponse(
        message=f"Node {node.key!r} written.",
        data=NodeResponse.model_validate(node.as_dict()),
        meta=_meta(),
    )


# ---- literal collections (must precede "/nodes/{node_key}") ----------


@router.get(
    "/topology",
    response_model=SuccessResponse[SubgraphResponse],
    summary="The subgraph around one node",
)
async def topology(
    organization_id: UUID,
    root_key: str,
    graph: GraphSvc,
    caller: CurrentUserId,
    depth: Annotated[int, Query(ge=1, le=15)] = 2,
    direction: TraversalDirection = TraversalDirection.BOTH,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
    node_types: Annotated[list[NodeType] | None, Query()] = None,
) -> SuccessResponse[SubgraphResponse]:
    """Return the subgraph around one node ("TOPOLOGY").

    This is what the dashboard, monitoring, automation, validation,
    workflow, and AI-assistant services consume.
    """
    del caller
    result = await graph.topology(
        organization_id,
        root_key,
        depth=depth,
        direction=direction,
        relationship_types=relationship_types,
        node_types=node_types,
    )
    return SuccessResponse(
        message=(
            "Topology rendered."
            if not result.truncated
            else "Topology rendered, truncated at the node ceiling."
        ),
        data=_subgraph(result.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/dependencies",
    response_model=SuccessResponse[AnalysisResponse],
    summary="What a node depends on",
)
async def dependencies(
    organization_id: UUID,
    node_key: str,
    analytics: AnalyticsSvc,
    caller: CurrentUserId,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
) -> SuccessResponse[AnalysisResponse]:
    """Answer "what does this need?" -- outward along dependency edges."""
    result = await analytics.dependencies(
        organization_id,
        node_key,
        depth=depth,
        relationship_types=relationship_types,
        actor_id=caller,
    )
    return SuccessResponse(
        message=f"{result.affected_count} dependencies found.",
        data=AnalysisResponse.model_validate(result.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/impact",
    response_model=SuccessResponse[AnalysisResponse],
    summary="What breaks if a node changes",
)
async def impact(
    organization_id: UUID,
    node_key: str,
    analytics: AnalyticsSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
) -> SuccessResponse[AnalysisResponse]:
    """Answer "what breaks if I change this?" -- inward along dependencies.

    The result is stored, because an impact number gets quoted in a
    change review hours after the graph has moved on.
    """
    result = await analytics.impact(
        organization_id,
        node_key,
        depth=depth,
        relationship_types=relationship_types,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.QUERIED,
        entity_type="impact_analysis",
        entity_key=node_key,
        actor_id=caller,
        context={"affected": result.affected_count, "severity": str(result.severity)},
    )
    return SuccessResponse(
        message=f"{result.affected_count} nodes affected, severity {result.severity}.",
        data=AnalysisResponse.model_validate(result.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/blast-radius",
    response_model=SuccessResponse[AnalysisResponse],
    summary="What fails if a node fails",
)
async def blast_radius(
    organization_id: UUID,
    node_key: str,
    analytics: AnalyticsSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
) -> SuccessResponse[AnalysisResponse]:
    """Answer "what fails if this fails, and how badly?" ("BLAST RADIUS")."""
    result = await analytics.blast_radius(
        organization_id,
        node_key,
        depth=depth,
        relationship_types=relationship_types,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.QUERIED,
        entity_type="blast_radius",
        entity_key=node_key,
        actor_id=caller,
        context={"affected": result.affected_count, "risk_score": result.risk_score},
    )
    return SuccessResponse(
        message=(
            f"{result.affected_count} nodes in the blast radius, " f"severity {result.severity}."
        ),
        data=AnalysisResponse.model_validate(result.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/path",
    response_model=SuccessResponse[SubgraphResponse],
    summary="The shortest path between two nodes",
)
async def shortest_path(
    organization_id: UUID,
    from_key: str,
    to_key: str,
    graph: GraphSvc,
    caller: CurrentUserId,
    max_depth: Annotated[int, Query(ge=1, le=15)] = 6,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
) -> SuccessResponse[SubgraphResponse]:
    """Return the shortest path, or an empty subgraph if unconnected.

    Empty is a real answer -- "these are not connected" -- rather than a
    failure.
    """
    del caller
    result = await graph.shortest_path(
        organization_id,
        from_key=from_key,
        to_key=to_key,
        relationship_types=relationship_types,
        max_depth=max_depth,
    )
    return SuccessResponse(
        message=(
            f"Path found across {len(result.nodes)} nodes."
            if result.nodes
            else "These nodes are not connected."
        ),
        data=_subgraph(result.as_dict()),
        meta=_meta(),
    )


# ---- relationships ---------------------------------------------------


@router.get(
    "/relationships",
    response_model=SuccessResponse[list[RelationshipResponse]],
    summary="List relationships",
)
async def list_relationships(
    organization_id: UUID,
    graph: GraphSvc,
    caller: CurrentUserId,
    node_key: str | None = None,
    relationship_types: Annotated[list[RelationshipType] | None, Query()] = None,
    direction: TraversalDirection = TraversalDirection.BOTH,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[RelationshipResponse]]:
    """Return relationships, optionally those around one node."""
    del caller
    edges = await graph.list_relationships(
        organization_id,
        node_key=node_key,
        relationship_types=relationship_types,
        direction=direction,
        limit=limit,
    )
    return SuccessResponse(
        message=f"Found {len(edges)} relationships.",
        data=[RelationshipResponse.model_validate(edge.as_dict()) for edge in edges],
        meta=_meta(),
    )


@router.post(
    "/relationships",
    response_model=SuccessResponse[RelationshipResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a relationship",
)
async def create_relationship(
    organization_id: UUID,
    body: RelationshipCreateRequest,
    graph: GraphSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RelationshipResponse]:
    """Create one relationship between two existing nodes.

    Both endpoints must already exist -- an edge is created between
    nodes, never conjuring them. A write that could invent endpoints
    would paper over its own ordering bugs with half-populated nodes.
    """
    edge = await graph.create_relationship(
        organization_id,
        RelationshipInput(
            from_key=body.from_key,
            to_key=body.to_key,
            relationship_type=body.relationship_type,
            weight=body.weight,
            properties=body.properties,
        ),
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.RELATIONSHIP_CHANGED,
        entity_type="relationship",
        entity_key=edge.relationship_key,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Relationship written.",
        data=RelationshipResponse.model_validate(edge.as_dict()),
        meta=_meta(),
    )


@router.delete(
    "/relationships/{relationship_key:path}",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Delete a relationship",
)
async def delete_relationship(
    relationship_key: str,
    organization_id: UUID,
    graph: GraphSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, bool]]:
    """Delete one relationship by its derived key.

    The key is ``from|TYPE|to``, matching what every read returns.
    Neo4j's own relationship ids are internal and unstable across a
    restore, which is why the identifier is derived rather than stored.

    Raises:
        ValidationError: If the key is not in the expected shape.
    """
    parts = relationship_key.split("|")
    expected_parts = 3
    if len(parts) != expected_parts:
        raise ValidationError(
            f"Relationship key {relationship_key!r} is not in the expected " "'from|TYPE|to' shape."
        )
    from_key, raw_type, to_key = parts
    removed = await graph.delete_relationship(
        organization_id,
        from_key=from_key,
        to_key=to_key,
        relationship_type=RelationshipType(raw_type),
        actor_id=caller,
    )
    if removed:
        await audit.record(
            organization_id=organization_id,
            action=AuditAction.RELATIONSHIP_CHANGED,
            entity_type="relationship",
            entity_key=relationship_key,
            actor_id=caller,
            context={"deleted": True},
        )
    return SuccessResponse(
        message="Relationship deleted." if removed else "No such relationship.",
        data={"deleted": removed},
        meta=_meta(),
    )


# ---- digital twins ---------------------------------------------------


@router.get(
    "/twins",
    response_model=SuccessResponse[list[TwinSummary]],
    summary="List tracked digital twins",
)
async def list_twins(
    organization_id: UUID,
    twins: TwinSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[TwinSummary]]:
    """Return the twins an organization tracks."""
    del caller
    rows = await twins.list_twins(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} tracked twins.",
        data=[TwinSummary.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/twins/{node_key:path}",
    response_model=SuccessResponse[TwinResponse],
    summary="One digital twin",
)
async def get_twin(
    node_key: str,
    organization_id: UUID,
    twins: TwinSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TwinResponse]:
    """Assemble the twin for one node.

    Health is composed on read as the worst among the node and its
    components -- a host reporting healthy while its database is down is
    not a useful statement about the host.
    """
    del caller
    twin = await twins.build(organization_id, node_key)
    return SuccessResponse(
        message=f"Twin for {node_key!r} assembled.",
        data=TwinResponse.model_validate(twin.as_dict()),
        meta=_meta(),
    )


@router.put(
    "/twins/{node_key:path}",
    response_model=SuccessResponse[TwinSummary],
    summary="Record twin state",
)
async def set_twin_state(
    node_key: str,
    organization_id: UUID,
    body: TwinStateRequest,
    twins: TwinSvc,
    caller: CurrentUserId,
) -> SuccessResponse[TwinSummary]:
    """Record lifecycle, health, criticality, ownership, and tags."""
    stored = await twins.set_state(
        organization_id,
        node_key,
        lifecycle_state=body.lifecycle_state,
        health_status=HealthStatus(body.health_status) if body.health_status else None,
        criticality=body.criticality,
        owner_team=body.owner_team,
        tags=body.tags,
        attributes=body.attributes,
        is_pinned=body.is_pinned,
        actor_id=caller,
    )
    return SuccessResponse(
        message=f"Twin state recorded for {node_key!r}.",
        data=TwinSummary.model_validate(stored),
        meta=_meta(),
    )


# ---- one node (declared last) ----------------------------------------


@router.get(
    "/nodes/{node_key:path}",
    response_model=SuccessResponse[NodeResponse],
    summary="Get one node",
)
async def get_node(
    node_key: str,
    organization_id: UUID,
    graph: GraphSvc,
    caller: CurrentUserId,
) -> SuccessResponse[NodeResponse]:
    """Return one node by its business key."""
    del caller
    node = await graph.get_node(organization_id, node_key)
    return SuccessResponse(
        message="Node retrieved.",
        data=NodeResponse.model_validate(node.as_dict()),
        meta=_meta(),
    )


@router.put(
    "/nodes/{node_key:path}",
    response_model=SuccessResponse[NodeResponse],
    summary="Update one node",
)
async def update_node(
    node_key: str,
    organization_id: UUID,
    body: NodeCreateRequest,
    graph: GraphSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[NodeResponse]:
    """Update one node.

    Raises:
        ValidationError: If the body's key does not match the path. A
            mismatch would silently write a different node than the URL
            names.
    """
    if body.key != node_key:
        raise ValidationError(
            f"The body key {body.key!r} does not match the path key {node_key!r}."
        )
    node = await graph.create_node(
        organization_id,
        NodeInput(
            key=node_key,
            node_type=body.node_type,
            name=body.name,
            description=body.description,
            project_id=body.project_id,
            source=body.source,
            properties=body.properties,
        ),
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.NODE_CHANGED,
        entity_type="node",
        entity_key=node.key,
        actor_id=caller,
    )
    return SuccessResponse(
        message=f"Node {node_key!r} updated.",
        data=NodeResponse.model_validate(node.as_dict()),
        meta=_meta(),
    )


@router.delete(
    "/nodes/{node_key:path}",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Delete one node",
)
async def delete_node(
    node_key: str,
    organization_id: UUID,
    graph: GraphSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, bool]]:
    """Delete one node, its relationships, and its metadata."""
    removed = await graph.delete_node(organization_id, node_key, actor_id=caller)
    if removed:
        await audit.record(
            organization_id=organization_id,
            action=AuditAction.NODE_CHANGED,
            entity_type="node",
            entity_key=node_key,
            actor_id=caller,
            context={"deleted": True},
        )
    return SuccessResponse(
        message="Node deleted." if removed else "No such node.",
        data={"deleted": removed},
        meta=_meta(),
    )


__all__ = ["router"]
