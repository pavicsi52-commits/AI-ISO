"""Graph search ("SEARCH").

Full-text over node names, descriptions, and keys, plus exact property
and metadata filtering, with sorting and pagination.

**Tenant scoping here is a predicate, not an index prefix**, and that is
worth knowing. Every other query in this service leads with
``organization_id`` in a composite index. A Neo4j full-text index is
over the listed properties only -- it cannot lead with the tenant -- so
the filter is applied to the *results* inside the same query. It is
still applied on every path; it just cannot be enforced by the index,
which is why the ``organization_id`` parameter is not optional anywhere
below.

**The search term is a bound parameter.** Lucene syntax is escaped
before binding, so a caller cannot turn a search box into a query
against the whole index by typing ``*:*``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.cypher.builder import (
    label_clause,
    order_clause,
    validate_limit,
    validate_property_name,
)
from app.graph.client import GraphClient
from app.graph.entities import GraphNode
from app.graph.schema import GRAPH_NODE_LABEL
from app.models.enums import NodeType
from app.models.graph_metadata import GraphMetadata
from app.repositories.graph_metadata import GraphMetadataRepository

FULLTEXT_INDEX = "graph_node_search"
"""The index declared by :mod:`app.graph.schema`."""

_MAX_LIMIT = 1_000
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')

SORTABLE_FIELDS = frozenset({"name", "key", "node_type", "created_at", "updated_at"})
"""Properties a caller may sort by.

A closed set, because an ``ORDER BY`` property name is part of the query
text and cannot be bound. Anything else is refused rather than escaped.
"""


def escape_lucene(term: str) -> str:
    """Escape Lucene's operators so a term is matched literally.

    Without this, ``*:*`` matches the entire index and ``a OR b``
    silently changes the query's meaning -- a search box that quietly
    accepts query syntax is a search box that leaks.
    """
    return _LUCENE_SPECIAL.sub(r"\\\1", term)


def build_search_term(query: str, *, fuzzy: bool = False) -> str:
    """Turn a caller's text into a safe Lucene query.

    Each word is escaped and the words are ANDed, so a two-word search
    narrows rather than widens. With *fuzzy*, a single-character edit
    distance is allowed per word -- enough for a typo, not enough to
    match an unrelated host.

    Raises:
        ValidationError: If the query has no searchable content.
    """
    words = [escape_lucene(word) for word in query.split() if word.strip()]
    if not words:
        raise ValidationError("A search needs at least one term.")
    if fuzzy:
        return " AND ".join(f"{word}~1" for word in words)
    return " AND ".join(words)


@dataclass(slots=True)
class SearchHit:
    """One node matched by a search, with its metadata if it has any."""

    node: GraphNode
    score: float = 0.0
    metadata: GraphMetadata | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        payload: dict[str, Any] = {**self.node.as_dict(), "score": round(self.score, 4)}
        if self.metadata is not None:
            payload["metadata"] = {
                "twin_type": str(self.metadata.twin_type) if self.metadata.twin_type else None,
                "lifecycle_state": str(self.metadata.lifecycle_state),
                "health_status": self.metadata.health_status,
                "criticality": self.metadata.criticality,
                "owner_team": self.metadata.owner_team,
                "tags": list(self.metadata.tags or []),
            }
        return payload


@dataclass(slots=True)
class SearchResults:
    """One page of search results."""

    hits: list[SearchHit] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
    truncated: bool = False

    @property
    def has_more(self) -> bool:
        """Whether another page exists."""
        return self.offset + len(self.hits) < self.total

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "hits": [hit.as_dict() for hit in self.hits],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "has_more": self.has_more,
            "truncated": self.truncated,
        }


class SearchEngine:
    """Searches nodes by text, properties, and metadata."""

    def __init__(
        self,
        client: GraphClient,
        metadata: GraphMetadataRepository,
        *,
        max_results: int = 1_000,
    ) -> None:
        self._client = client
        self._metadata = metadata
        self._max_results = max_results

    async def search(
        self,
        organization_id: UUID,
        query: str,
        *,
        node_types: list[NodeType] | None = None,
        fuzzy: bool = False,
        limit: int = 50,
        offset: int = 0,
        enrich: bool = True,
    ) -> SearchResults:
        """Full-text search across node names, descriptions, and keys.

        Raises:
            ValidationError: If the query or paging parameters are invalid.
            DependencyError: If the graph is unreachable.
        """
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        term = build_search_term(query, fuzzy=fuzzy)
        labels = label_clause(node_types)

        cypher = (
            f"CALL db.index.fulltext.queryNodes($index, $term) YIELD node AS n, score "
            f"WHERE n:{GRAPH_NODE_LABEL}{labels} "
            "  AND n.organization_id = $organization_id "
            "RETURN properties(n) AS node, score "
            "ORDER BY score DESC, n.name ASC "
            "SKIP $offset LIMIT $limit"
        )
        result = await self._client.read(
            cypher,
            {
                "index": FULLTEXT_INDEX,
                "term": term,
                "organization_id": str(organization_id),
                "offset": max(0, offset),
                "limit": safe_limit,
            },
            max_records=safe_limit,
        )
        hits = [
            SearchHit(
                node=GraphNode.from_record(row.get("node", {})),
                score=float(row.get("score") or 0.0),
            )
            for row in result.records
        ]
        if enrich:
            await self._enrich(organization_id, hits)

        total = await self._count(organization_id, term, node_types)
        return SearchResults(
            hits=hits,
            total=total,
            offset=max(0, offset),
            limit=safe_limit,
            truncated=result.truncated,
        )

    async def search_by_property(
        self,
        organization_id: UUID,
        *,
        property_name: str,
        value: Any,
        node_types: list[NodeType] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = "name",
        descending: bool = False,
    ) -> SearchResults:
        """Exact match on one node property ("Property Search").

        Raises:
            ValidationError: If the property or sort field is not
                permitted, or the paging parameters are invalid.
        """
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        if sort_by is not None and sort_by not in SORTABLE_FIELDS:
            permitted = ", ".join(sorted(SORTABLE_FIELDS))
            raise ValidationError(f"Cannot sort by {sort_by!r}. Sortable fields: {permitted}.")
        # The property *name* is part of the query text, so it is
        # validated as an identifier. The property *value* is bound.
        safe_property = validate_property_name(property_name)
        cypher = (
            f"MATCH (n:{GRAPH_NODE_LABEL}{label_clause(node_types)} "
            "{organization_id: $organization_id}) "
            f"WHERE n.{safe_property} = $value "
            "RETURN properties(n) AS node"
            f"{order_clause('n', sort_by, descending=descending)} "
            "SKIP $offset LIMIT $limit"
        )
        result = await self._client.read(
            cypher,
            {
                "organization_id": str(organization_id),
                "value": value,
                "offset": max(0, offset),
                "limit": safe_limit,
            },
            max_records=safe_limit,
        )
        hits = [
            SearchHit(node=GraphNode.from_record(row.get("node", {}))) for row in result.records
        ]
        await self._enrich(organization_id, hits)
        return SearchResults(
            hits=hits,
            total=len(hits),
            offset=max(0, offset),
            limit=safe_limit,
            truncated=result.truncated,
        )

    async def search_metadata(
        self,
        organization_id: UUID,
        *,
        tags: list[str] | None = None,
        owner_team: str | None = None,
        min_criticality: float | None = None,
        limit: int = 100,
    ) -> list[GraphMetadata]:
        """Search the PostgreSQL metadata side ("Metadata Search").

        Filtered in Python after a scoped fetch rather than in SQL: tags
        are a JSON array, and a portable containment predicate across
        SQLite and PostgreSQL is more trouble than filtering a bounded
        result set. The scope keeps that set bounded.
        """
        rows = await self._metadata.list_for_org(organization_id, limit=limit)
        wanted = set(tags or [])
        return [
            row
            for row in rows
            if (not wanted or wanted <= set(row.tags or []))
            and (owner_team is None or row.owner_team == owner_team)
            and (min_criticality is None or row.criticality >= min_criticality)
        ]

    async def _count(
        self,
        organization_id: UUID,
        term: str,
        node_types: list[NodeType] | None,
    ) -> int:
        """How many nodes match, for paging.

        A second query rather than counting the page: a caller needs to
        know there are four hundred matches while looking at the first
        fifty, and the page cannot tell them that.
        """
        cypher = (
            "CALL db.index.fulltext.queryNodes($index, $term) YIELD node AS n "
            f"WHERE n:{GRAPH_NODE_LABEL}{label_clause(node_types)} "
            "  AND n.organization_id = $organization_id "
            "RETURN count(n) AS total"
        )
        result = await self._client.read(
            cypher,
            {
                "index": FULLTEXT_INDEX,
                "term": term,
                "organization_id": str(organization_id),
            },
        )
        return int(result.scalar("total", 0) or 0)

    async def _enrich(self, organization_id: UUID, hits: list[SearchHit]) -> None:
        """Attach metadata to hits in one batched read.

        One query for every hit rather than one per hit: a fifty-result
        page would otherwise be fifty round trips to decorate a list.
        """
        if not hits:
            return
        found = await self._metadata.get_many(organization_id, [hit.node.key for hit in hits])
        for hit in hits:
            hit.metadata = found.get(hit.node.key)


__all__ = [
    "FULLTEXT_INDEX",
    "SORTABLE_FIELDS",
    "SearchEngine",
    "SearchHit",
    "SearchResults",
    "build_search_term",
    "escape_lucene",
]
