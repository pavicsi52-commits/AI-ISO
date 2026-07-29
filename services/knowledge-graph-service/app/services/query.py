"""Graph query execution ("GRAPH QUERIES").

Two paths, and the distinction is the security boundary:

- **Built-in queries** -- the catalogue below. This service wrote the
  Cypher; the caller supplies only bound parameters.
- **Custom Cypher** -- the caller wrote it. Refused unless
  :mod:`app.cypher.guard` clears it, then run in an explicitly *read*
  transaction so Neo4j refuses a write even if the guard were bypassed.

**Saved queries stay parameterised through storage.** A saved query
holds Cypher and a parameter *schema*; execution binds the caller's
values against that schema rather than substituting them into the text.
Storing a formatted string instead would turn the saved-query table into
a stored-procedure-shaped injection hole.

**Every execution is recorded**, successful or not, with its parameters
kept separate from its text. That is both the audit trail docs/049 asks
for and how a slow traversal gets traced back to what produced it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.cypher import guard
from app.cypher.builder import traversal_pattern, validate_limit
from app.graph.client import GraphClient
from app.graph.schema import GRAPH_NODE_LABEL
from app.models.enums import QueryKind, RelationshipType, TraversalDirection
from app.models.graph_query import GraphQuery
from app.models.graph_saved_query import GraphSavedQuery
from app.repositories.graph_query import GraphQueryRepository
from app.repositories.graph_saved_query import GraphSavedQueryRepository

logger = get_logger("app.services.query")

_MAX_ROWS = 5_000


def kind_of(record: GraphSavedQuery) -> QueryKind:
    """A saved query's kind as a genuine enum member.

    ``kind`` is annotated ``Mapped[QueryKind]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = record.kind
    return value if isinstance(value, QueryKind) else QueryKind(value)


def _ownership_cypher() -> str:
    """Who owns what ("Ownership Queries")."""
    pattern = traversal_pattern(
        direction=TraversalDirection.OUTGOING, types=[RelationshipType.OWNS]
    )
    return (
        f"MATCH (owner:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}})"
        f"{pattern}(asset:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
        "RETURN owner.key AS owner_key, owner.name AS owner_name, "
        "       asset.key AS asset_key, asset.name AS asset_name, "
        "       asset.node_type AS asset_type "
        "ORDER BY owner_name, asset_name LIMIT $limit"
    )


def _dependency_cypher(types: list[RelationshipType], direction: TraversalDirection) -> str:
    """One dependency-flavoured query over a given edge set."""
    pattern = traversal_pattern(direction=direction, types=types, depth=3, ceiling=6)
    return (
        f"MATCH (root:{GRAPH_NODE_LABEL} "
        "{key: $root_key, organization_id: $organization_id}) "
        f"MATCH path = (root){pattern}"
        f"(other:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
        "RETURN DISTINCT other.key AS key, other.name AS name, "
        "       other.node_type AS node_type, length(path) AS distance "
        "ORDER BY distance, name LIMIT $limit"
    )


BUILTIN_QUERIES: dict[QueryKind, str] = {
    QueryKind.OWNERSHIP: _ownership_cypher(),
    QueryKind.SERVICE_DEPENDENCY: _dependency_cypher(
        [RelationshipType.DEPENDS_ON, RelationshipType.COMMUNICATES_WITH],
        TraversalDirection.OUTGOING,
    ),
    QueryKind.CONFIGURATION_DEPENDENCY: _dependency_cypher(
        [RelationshipType.CONFIGURES], TraversalDirection.INCOMING
    ),
    QueryKind.AUTOMATION_DEPENDENCY: _dependency_cypher(
        [RelationshipType.EXECUTES, RelationshipType.USES], TraversalDirection.OUTGOING
    ),
    QueryKind.WORKFLOW_DEPENDENCY: _dependency_cypher(
        [RelationshipType.EXECUTES], TraversalDirection.OUTGOING
    ),
}
"""The catalogue of queries this service wrote ("GRAPH QUERIES").

Built through :mod:`app.cypher.builder`, so every label, relationship
type, and depth in them was validated at import time rather than at
request time. A caller names a kind and supplies parameters; they never
supply text.
"""

_REQUIRED_PARAMETERS: dict[QueryKind, tuple[str, ...]] = {
    QueryKind.OWNERSHIP: ("organization_id", "limit"),
    QueryKind.SERVICE_DEPENDENCY: ("organization_id", "root_key", "limit"),
    QueryKind.CONFIGURATION_DEPENDENCY: ("organization_id", "root_key", "limit"),
    QueryKind.AUTOMATION_DEPENDENCY: ("organization_id", "root_key", "limit"),
    QueryKind.WORKFLOW_DEPENDENCY: ("organization_id", "root_key", "limit"),
}


@dataclass(slots=True)
class QueryOutcome:
    """The result of one query execution."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    truncated: bool = False
    kind: QueryKind = QueryKind.CUSTOM_CYPHER

    @property
    def row_count(self) -> int:
        """How many rows came back."""
        return len(self.rows)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "kind": str(self.kind),
            "rows": self.rows,
            "row_count": self.row_count,
            "duration_ms": round(self.duration_ms, 2),
            "truncated": self.truncated,
        }


class QueryService:
    """Runs built-in, saved, and custom graph queries."""

    def __init__(
        self,
        client: GraphClient,
        queries: GraphQueryRepository,
        saved: GraphSavedQueryRepository,
        *,
        allow_custom_cypher: bool = True,
        max_rows: int = _MAX_ROWS,
    ) -> None:
        self._client = client
        self._queries = queries
        self._saved = saved
        self._allow_custom = allow_custom_cypher
        self._max_rows = max_rows

    async def run_builtin(
        self,
        organization_id: UUID,
        kind: QueryKind,
        *,
        parameters: dict[str, Any] | None = None,
        limit: int = 200,
        actor_id: UUID | None = None,
    ) -> QueryOutcome:
        """Run one query from the built-in catalogue.

        Raises:
            ValidationError: If the kind has no built-in query or a
                required parameter is missing.
            DependencyError: If the graph is unreachable.
        """
        cypher = BUILTIN_QUERIES.get(kind)
        if cypher is None:
            supported = ", ".join(sorted(str(one) for one in BUILTIN_QUERIES))
            raise ValidationError(
                f"No built-in query for {str(kind)!r}. Available: {supported}. "
                "Use POST /graph/cypher for anything else."
            )

        bound: dict[str, Any] = {
            "organization_id": str(organization_id),
            "limit": validate_limit(limit, ceiling=self._max_rows),
            **(parameters or {}),
        }
        missing = [name for name in _REQUIRED_PARAMETERS.get(kind, ()) if name not in bound]
        if missing:
            raise ValidationError(
                f"Query {str(kind)!r} needs these parameters: {', '.join(missing)}."
            )
        return await self._execute(organization_id, cypher, bound, kind=kind, actor_id=actor_id)

    async def run_custom(
        self,
        organization_id: UUID,
        cypher: str,
        *,
        parameters: dict[str, Any] | None = None,
        limit: int = 200,
        actor_id: UUID | None = None,
    ) -> QueryOutcome:
        """Run caller-authored Cypher, read-only.

        Raises:
            ConflictError: If custom Cypher is disabled on this
                deployment.
            ValidationError: If the statement is not safely read-only or
                references an unbound parameter.
            DependencyError: If the graph is unreachable or Neo4j
                refuses it.
        """
        if not self._allow_custom:
            raise ConflictError(
                "Custom Cypher is disabled on this deployment. Use the built-in "
                "query kinds or a saved query."
            )

        bound: dict[str, Any] = {
            "organization_id": str(organization_id),
            "limit": validate_limit(limit, ceiling=self._max_rows),
            **(parameters or {}),
        }
        # Order matters: refuse before executing, so a rejection is
        # audited as DENIED and the caller gets a message naming the
        # clause rather than a driver error.
        guard.require_read_only(cypher)
        guard.require_bound_parameters(cypher, bound)

        return await self._execute(
            organization_id,
            cypher,
            bound,
            kind=QueryKind.CUSTOM_CYPHER,
            actor_id=actor_id,
        )

    async def run_saved(
        self,
        organization_id: UUID,
        slug: str,
        *,
        parameters: dict[str, Any] | None = None,
        limit: int = 200,
        actor_id: UUID | None = None,
    ) -> QueryOutcome:
        """Run a stored query with the caller's parameters bound.

        Raises:
            NotFoundError: If no saved query has that slug.
            ValidationError: If a declared parameter was not supplied.
            DependencyError: If the graph is unreachable.
        """
        record = await self._saved.get_by_slug(organization_id, slug)
        if record is None:
            raise NotFoundError(f"No saved query with slug {slug!r}.")

        bound: dict[str, Any] = {
            "organization_id": str(organization_id),
            "limit": validate_limit(limit, ceiling=self._max_rows),
            **(record.default_parameters or {}),
            **(parameters or {}),
        }
        declared = set(record.parameter_schema or {})
        missing = sorted(declared - set(bound))
        if missing:
            raise ValidationError(
                f"Saved query {slug!r} declares parameters that were not "
                f"supplied: {', '.join(missing)}."
            )
        guard.require_read_only(record.cypher)
        guard.require_bound_parameters(record.cypher, bound)

        outcome = await self._execute(
            organization_id,
            record.cypher,
            bound,
            kind=kind_of(record),
            actor_id=actor_id,
            saved_query_id=record.id,
        )
        record.execution_count += 1
        await self._saved.update(record)
        return outcome

    async def save_query(
        self,
        organization_id: UUID,
        *,
        slug: str,
        name: str,
        cypher: str,
        description: str | None = None,
        kind: QueryKind = QueryKind.CUSTOM_CYPHER,
        parameter_schema: dict[str, Any] | None = None,
        default_parameters: dict[str, Any] | None = None,
        owner_id: UUID | None = None,
    ) -> GraphSavedQuery:
        """Store a reusable query, validated read-only at save time.

        Checked here as well as at execution: a statement that could
        never run safely should be refused when someone writes it, not
        the first time somebody else runs it.

        Raises:
            ConflictError: If the slug is already used.
            ValidationError: If the Cypher is not safely read-only.
        """
        if await self._saved.get_by_slug(organization_id, slug) is not None:
            raise ConflictError(f"A saved query with slug {slug!r} already exists.")
        guard.require_read_only(cypher)
        return await self._saved.create(
            GraphSavedQuery(
                organization_id=organization_id,
                slug=slug,
                name=name,
                description=description,
                kind=kind,
                cypher=cypher,
                parameter_schema=parameter_schema or {},
                default_parameters=default_parameters or {},
                owner_id=owner_id,
            )
        )

    async def list_saved(self, organization_id: UUID) -> list[GraphSavedQuery]:
        """Saved queries for one organization."""
        return await self._saved.list_for_org(organization_id)

    async def delete_saved(self, organization_id: UUID, slug: str) -> bool:
        """Delete a saved query; returns whether it existed.

        Raises:
            ConflictError: If it is a built-in system query.
        """
        record = await self._saved.get_by_slug(organization_id, slug)
        if record is None:
            return False
        if record.is_system:
            raise ConflictError(
                "Built-in saved queries cannot be deleted; copy one and change the copy."
            )
        await self._saved.purge(record.id)
        return True

    async def history(
        self,
        organization_id: UUID,
        *,
        kind: QueryKind | None = None,
        failed_only: bool = False,
        limit: int = 200,
    ) -> list[GraphQuery]:
        """Executed queries, most recent first."""
        return await self._queries.list_for_org(
            organization_id, kind=kind, failed_only=failed_only, limit=limit
        )

    async def slowest(self, organization_id: UUID, *, limit: int = 10) -> list[GraphQuery]:
        """The slowest recorded queries, for tuning."""
        return await self._queries.slowest(organization_id, limit=limit)

    async def _execute(
        self,
        organization_id: UUID,
        cypher: str,
        parameters: dict[str, Any],
        *,
        kind: QueryKind,
        actor_id: UUID | None,
        saved_query_id: UUID | None = None,
    ) -> QueryOutcome:
        """Run one statement and record it, whatever the result.

        A failed query is recorded too. A history containing only
        successes cannot answer "what has been failing since the
        upgrade?", which is the question it is usually opened for.
        """
        started = time.monotonic()
        error: str | None = None
        outcome = QueryOutcome(kind=kind)
        try:
            result = await self._client.read(cypher, parameters, max_records=self._max_rows)
            outcome.rows = result.records
            outcome.duration_ms = result.duration_ms
            outcome.truncated = result.truncated
        except Exception as exc:
            error = str(exc)
            outcome.duration_ms = (time.monotonic() - started) * 1000
            raise
        finally:
            await self._record(
                organization_id,
                cypher=cypher,
                parameters=parameters,
                kind=kind,
                outcome=outcome,
                error=error,
                actor_id=actor_id,
                saved_query_id=saved_query_id,
            )
        return outcome

    async def _record(
        self,
        organization_id: UUID,
        *,
        cypher: str,
        parameters: dict[str, Any],
        kind: QueryKind,
        outcome: QueryOutcome,
        error: str | None,
        actor_id: UUID | None,
        saved_query_id: UUID | None,
    ) -> None:
        """Append one execution record, best-effort.

        Swallowed on failure for the same reason auditing is: losing the
        record of a query is better than failing a query that already
        returned its answer.
        """
        try:
            await self._queries.create(
                GraphQuery(
                    organization_id=organization_id,
                    kind=kind,
                    cypher=cypher,
                    parameters={k: v for k, v in parameters.items() if k != "organization_id"},
                    saved_query_id=saved_query_id,
                    succeeded=error is None,
                    row_count=outcome.row_count,
                    truncated=outcome.truncated,
                    duration_ms=outcome.duration_ms,
                    error=error,
                    executed_by=actor_id,
                    executed_at=datetime.now(UTC),
                )
            )
        except Exception as exc:
            logger.warning(
                "Could not record a graph query execution.",
                extra={"extra_fields": {"error": str(exc)}},
            )


__all__ = ["BUILTIN_QUERIES", "QueryOutcome", "QueryService", "kind_of"]
