"""The Neo4j client: driver lifecycle and query execution (docs/060
"KNOWLEDGE GRAPH QUERY" tool kind, "Knowledge Graph Reasoning" mode).

Mirrors ``knowledge-graph-service``'s own ``app/graph/client.py``
(Prompt 049) shape closely -- rewritten here, not imported, per this
platform's zero-cross-service-import convention. ``shared_core``
provides ``Neo4jSettings`` and a TCP-reachability check but no driver
wrapper (the gap ``services/inventory-service`` first documented), so
this depends on the official ``neo4j`` async driver directly.

**Reads and writes go through different methods, and that is load-
bearing.** :meth:`GraphClient.read` opens an explicitly read
transaction, so a Knowledge Graph Query tool call containing a write
clause fails at the database rather than on this service's own say-so
-- an agent's own tool call is caller-authored Cypher in exactly the
sense that matters here.

**Every result is bounded.** A traversal that would return more rows
than the configured ceiling is cut off and the result flagged
``truncated`` -- a partial answer that says so beats an unbounded one
that exhausts the process or the agent's own context window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from shared_core.config.settings import Neo4jSettings
from shared_core.exceptions.dependency import DependencyError
from shared_core.logging.logger import get_logger

logger = get_logger("app.graph.client")


def create_neo4j_driver(
    settings: Neo4jSettings,
    *,
    enabled: bool = True,
    max_pool_size: int = 50,
    connection_timeout: float = 30.0,
) -> AsyncDriver | None:
    """Build an :class:`~neo4j.AsyncDriver`, or ``None`` when disabled.

    The caller owns the lifetime -- close it at shutdown, the same "one
    client, built once at startup" shape every AI-IOS infrastructure
    client uses.

    Building never raises. The driver connects lazily, so a bad host
    surfaces as a failed readiness check and a failed query rather than
    a service that cannot boot.
    """
    if not enabled:
        return None
    try:
        return AsyncGraphDatabase.driver(
            settings.uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=max_pool_size,
            connection_acquisition_timeout=connection_timeout,
        )
    except Exception as exc:
        logger.warning(
            "Neo4j is unavailable; graph operations will report themselves failed.",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return None


@dataclass(slots=True)
class QueryResult:
    """Rows from one Cypher execution, with what it cost."""

    records: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    truncated: bool = False

    @property
    def row_count(self) -> int:
        """How many rows came back."""
        return len(self.records)

    def scalar(self, key: str, default: Any = None) -> Any:
        """One value from the first row, or *default* if there is none."""
        if not self.records:
            return default
        return self.records[0].get(key, default)


class GraphClient:
    """Executes Cypher against Neo4j."""

    def __init__(
        self,
        driver: AsyncDriver | None,
        *,
        database: str = "neo4j",
        max_records: int = 1_000,
        timeout_seconds: float = 30.0,
        enabled: bool = True,
    ) -> None:
        self._driver = driver
        self._database = database
        self._max_records = max_records
        self._timeout = timeout_seconds
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether the graph is configured and reachable on this deployment."""
        return self._enabled and self._driver is not None

    @property
    def database(self) -> str:
        """The Neo4j database this client targets."""
        return self._database

    def _require_driver(self) -> AsyncDriver:
        """The driver, or a clear failure.

        Raises:
            DependencyError: If the graph is unconfigured.
        """
        if not self.enabled or self._driver is None:
            raise DependencyError(
                "The knowledge graph is not configured on this deployment. "
                "Set AIIOS_NEO4J_HOST and "
                "AIIOS_AI_AGENT_PLATFORM_SERVICE_NEO4J_ENABLED."
            )
        return self._driver

    async def read(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
        *,
        max_records: int | None = None,
    ) -> QueryResult:
        """Run a statement in an explicitly **read** transaction.

        A write clause fails here at the database -- the guarantee
        behind the Knowledge Graph Query tool kind, whatever an agent's
        own generated Cypher tries to do.

        Raises:
            DependencyError: If the graph is unreachable or the query
                fails. The message carries the driver reason, which is
                what an operator needs.
        """
        driver = self._require_driver()
        ceiling = max_records or self._max_records
        started = time.monotonic()
        records: list[dict[str, Any]] = []
        truncated = False

        try:
            async with driver.session(
                database=self._database, default_access_mode="READ"
            ) as session:
                cursor = await session.run(cypher, parameters or {}, timeout=self._timeout)
                async for record in cursor:
                    if len(records) >= ceiling:
                        truncated = True
                        break
                    records.append(dict(record))
                if truncated:
                    await cursor.consume()
        except Exception as exc:
            logger.warning(
                "A graph read failed.",
                extra={"extra_fields": {"error": str(exc)}},
            )
            raise DependencyError(f"Graph query failed: {exc}") from exc

        if truncated:
            logger.warning(
                "A graph read hit the record ceiling; the result is truncated.",
                extra={"extra_fields": {"ceiling": ceiling}},
            )
        return QueryResult(
            records=records,
            duration_ms=(time.monotonic() - started) * 1000,
            truncated=truncated,
        )

    async def write(self, cypher: str, parameters: dict[str, Any] | None = None) -> QueryResult:
        """Run a statement in a write transaction.

        Only this service's own built-in statements reach here -- never
        agent- or caller-authored Cypher, which has no path to this
        method.

        Raises:
            DependencyError: If the graph is unreachable or the write
                fails.
        """
        driver = self._require_driver()
        started = time.monotonic()
        try:
            async with driver.session(
                database=self._database, default_access_mode="WRITE"
            ) as session:
                cursor = await session.run(cypher, parameters or {}, timeout=self._timeout)
                records = [dict(record) async for record in cursor]
        except Exception as exc:
            logger.warning(
                "A graph write failed.",
                extra={"extra_fields": {"error": str(exc)}},
            )
            raise DependencyError(f"Graph write failed: {exc}") from exc

        return QueryResult(records=records, duration_ms=(time.monotonic() - started) * 1000)

    async def verify(self) -> bool:
        """Whether the graph answers right now, for the readiness probe."""
        if not self.enabled or self._driver is None:
            return False
        try:
            await self._driver.verify_connectivity()
        except Exception:
            return False
        return True


__all__ = ["GraphClient", "QueryResult", "create_neo4j_driver"]
