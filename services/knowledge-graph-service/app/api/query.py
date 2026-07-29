"""Query, Cypher, search, and analytics endpoints.

``POST /graph/cypher`` is the most dangerous endpoint in this platform,
so its handler is the one place worth reading twice. The order is
deliberate:

1. Refuse it if the deployment has custom Cypher switched off.
2. Refuse it if :mod:`app.cypher.guard` finds a write clause, a
   forbidden procedure, or an unparameterised literal -- **and audit
   that refusal as ``DENIED``** before returning, because a probe that
   changes nothing would otherwise leave no trace at all.
3. Run it in an explicitly *read* transaction, so Neo4j refuses a write
   even if the guard has missed something.

The guard produces the good error message. Neo4j produces the guarantee.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AnalyticsSvc,
    AuditSvc,
    CurrentUserId,
    QuerySvc,
    SearchSvc,
)
from app.models.enums import AnalyticsAlgorithm, AuditAction, NodeType, QueryKind
from app.schemas.graph import (
    AnalyticsRequest,
    AnalyticsResponse,
    CypherRequest,
    GraphQueryRequest,
    QueryResultResponse,
    SavedQueryRequest,
    SavedQueryResponse,
    SearchResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/graph", tags=["Queries & Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/query",
    response_model=SuccessResponse[QueryResultResponse],
    summary="Run a built-in graph query",
)
async def run_query(
    organization_id: UUID,
    body: GraphQueryRequest,
    queries: QuerySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[QueryResultResponse]:
    """Run one query from the built-in catalogue.

    The caller names a kind and supplies parameters; they never supply
    query text. Every statement in the catalogue was built through
    :mod:`app.cypher.builder` at import time.
    """
    outcome = await queries.run_builtin(
        organization_id,
        body.kind,
        parameters=body.parameters,
        limit=body.limit,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.QUERIED,
        entity_type="graph_query",
        entity_key=str(body.kind),
        actor_id=caller,
        context={"rows": outcome.row_count},
    )
    return SuccessResponse(
        message=f"{outcome.row_count} rows.",
        data=QueryResultResponse.model_validate(outcome.as_dict()),
        meta=_meta(),
    )


@router.post(
    "/cypher",
    response_model=SuccessResponse[QueryResultResponse],
    summary="Run read-only Cypher",
)
async def run_cypher(
    organization_id: UUID,
    body: CypherRequest,
    queries: QuerySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[QueryResultResponse]:
    """Run caller-authored Cypher, read-only.

    A refusal is audited as ``DENIED`` before it is returned. Someone
    probing this endpoint with ``DETACH DELETE`` changes no state, so a
    trail recording only successful executions would show nothing at
    all -- and that probe is exactly what a reviewer is looking for.

    Raises:
        ConflictError: If custom Cypher is disabled here.
        ValidationError: If the statement is not safely read-only.
        DependencyError: If the graph is unreachable or refuses it.
    """
    try:
        outcome = await queries.run_custom(
            organization_id,
            body.cypher,
            parameters=body.parameters,
            limit=body.limit,
            actor_id=caller,
        )
    except ValidationError as exc:
        await audit.record_denied(
            organization_id=organization_id,
            action=AuditAction.CYPHER_EXECUTED,
            entity_type="cypher",
            reason=str(exc),
            actor_id=caller,
            context={"statement": body.cypher[:500]},
        )
        raise

    await audit.record(
        organization_id=organization_id,
        action=AuditAction.CYPHER_EXECUTED,
        entity_type="cypher",
        actor_id=caller,
        context={"statement": body.cypher[:500], "rows": outcome.row_count},
    )
    return SuccessResponse(
        message=f"{outcome.row_count} rows.",
        data=QueryResultResponse.model_validate(outcome.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/queries/saved",
    response_model=SuccessResponse[list[SavedQueryResponse]],
    summary="List saved queries",
)
async def list_saved_queries(
    organization_id: UUID, queries: QuerySvc, caller: CurrentUserId
) -> SuccessResponse[list[SavedQueryResponse]]:
    """Return the organization's saved queries."""
    del caller
    rows = await queries.list_saved(organization_id)
    return SuccessResponse(
        message=f"Found {len(rows)} saved queries.",
        data=[SavedQueryResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.post(
    "/queries/saved",
    response_model=SuccessResponse[SavedQueryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Save a reusable query",
)
async def save_query(
    organization_id: UUID,
    body: SavedQueryRequest,
    queries: QuerySvc,
    caller: CurrentUserId,
) -> SuccessResponse[SavedQueryResponse]:
    """Store a parameterised query, checked read-only at save time.

    Checked here as well as at execution: a statement that could never
    run safely should be refused when someone writes it, not the first
    time somebody else runs it.
    """
    record = await queries.save_query(
        organization_id,
        slug=body.slug,
        name=body.name,
        cypher=body.cypher,
        description=body.description,
        kind=body.kind,
        parameter_schema=body.parameter_schema,
        default_parameters=body.default_parameters,
        owner_id=caller,
    )
    return SuccessResponse(
        message=f"Saved query {record.slug!r} stored.",
        data=SavedQueryResponse.model_validate(record),
        meta=_meta(),
    )


@router.post(
    "/queries/saved/{slug}/run",
    response_model=SuccessResponse[QueryResultResponse],
    summary="Run a saved query",
)
async def run_saved_query(
    slug: str,
    organization_id: UUID,
    queries: QuerySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 200,
    parameters: dict[str, object] | None = None,
) -> SuccessResponse[QueryResultResponse]:
    """Run a stored query with the caller's parameters bound."""
    outcome = await queries.run_saved(
        organization_id,
        slug,
        parameters=dict(parameters or {}),
        limit=limit,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.QUERIED,
        entity_type="saved_query",
        entity_key=slug,
        actor_id=caller,
        context={"rows": outcome.row_count},
    )
    return SuccessResponse(
        message=f"{outcome.row_count} rows.",
        data=QueryResultResponse.model_validate(outcome.as_dict()),
        meta=_meta(),
    )


@router.delete(
    "/queries/saved/{slug}",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Delete a saved query",
)
async def delete_saved_query(
    slug: str, organization_id: UUID, queries: QuerySvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete a saved query. Built-in ones are refused."""
    del caller
    removed = await queries.delete_saved(organization_id, slug)
    return SuccessResponse(
        message="Saved query deleted." if removed else "No such saved query.",
        data={"deleted": removed},
        meta=_meta(),
    )


@router.get(
    "/queries/history",
    response_model=SuccessResponse[list[dict[str, object]]],
    summary="Executed query history",
)
async def query_history(
    organization_id: UUID,
    queries: QuerySvc,
    caller: CurrentUserId,
    kind: QueryKind | None = None,
    failed_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[dict[str, object]]]:
    """Return executed queries, most recent first.

    Failed executions are included. A history containing only successes
    cannot answer "what has been failing since the upgrade?", which is
    the question it is usually opened for.
    """
    del caller
    rows = await queries.history(organization_id, kind=kind, failed_only=failed_only, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} executions.",
        data=[
            {
                "id": str(row.id),
                "kind": str(row.kind),
                "succeeded": row.succeeded,
                "row_count": row.row_count,
                "duration_ms": row.duration_ms,
                "error": row.error,
                "executed_at": row.executed_at.isoformat(),
            }
            for row in rows
        ],
        meta=_meta(),
    )


@router.get(
    "/search",
    response_model=SuccessResponse[SearchResponse],
    summary="Search the graph",
)
async def search(
    organization_id: UUID,
    q: str,
    search_engine: SearchSvc,
    caller: CurrentUserId,
    node_types: Annotated[list[NodeType] | None, Query()] = None,
    fuzzy: bool = False,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[SearchResponse]:
    """Full-text search across node names, descriptions, and keys.

    Lucene operators in the query are escaped before binding, so a
    search for ``*:*`` looks for that literal text rather than matching
    the whole index.
    """
    del caller
    results = await search_engine.search(
        organization_id,
        q,
        node_types=node_types,
        fuzzy=fuzzy,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        message=f"{results.total} matches.",
        data=SearchResponse.model_validate(results.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/analytics",
    response_model=SuccessResponse[AnalyticsResponse],
    summary="Run a graph algorithm",
)
async def analytics(
    organization_id: UUID,
    algorithm: AnalyticsAlgorithm,
    analytics_service: AnalyticsSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AnalyticsResponse]:
    """Run one algorithm with default parameters.

    The ``POST`` form takes parameters; this exists because docs/049
    names ``GET /graph/analytics`` and the parameterless algorithms are
    the ones asked for most.
    """
    del caller
    outcome = await analytics_service.run(organization_id, algorithm)
    return SuccessResponse(
        message=f"{algorithm} computed over {outcome.node_count} nodes.",
        data=AnalyticsResponse.model_validate(outcome.as_dict()),
        meta=_meta(),
    )


@router.post(
    "/analytics",
    response_model=SuccessResponse[AnalyticsResponse],
    summary="Run a graph algorithm with parameters",
)
async def run_analytics(
    organization_id: UUID,
    body: AnalyticsRequest,
    analytics_service: AnalyticsSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AnalyticsResponse]:
    """Run one algorithm with explicit parameters.

    Raises:
        ValidationError: If the algorithm is unknown, a required
            parameter is missing, or the graph exceeds the analytics
            ceiling.
    """
    del caller
    outcome = await analytics_service.run(
        organization_id, body.algorithm, parameters=body.parameters
    )
    return SuccessResponse(
        message=f"{body.algorithm} computed over {outcome.node_count} nodes.",
        data=AnalyticsResponse.model_validate(outcome.as_dict()),
        meta=_meta(),
    )


__all__ = ["router"]
