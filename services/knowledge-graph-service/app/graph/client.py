"""The Neo4j client: driver lifecycle and query execution.

Per docs/049 "DATABASES": Neo4j stores graph entities and
relationships. This is the single place this service talks to it.

**Reads and writes go through different methods, and that is load-
bearing.** :meth:`GraphClient.read` opens an explicitly read
transaction, so a statement containing a write clause fails at the
database rather than on this service's say-so. That is what makes
``POST /graph/cypher`` safe even if :mod:`app.cypher.guard` ever misses
something: the guard produces the good error message, Neo4j produces the
guarantee.

**Every result is bounded.** A traversal that would return more rows
than the configured ceiling is cut off and the result flagged
``truncated`` -- a partial answer that says so beats an unbounded one
that exhausts the process.

``shared_core`` provides ``Neo4jSettings`` and a TCP-reachability check
but no driver wrapper (the gap ``services/inventory-service`` first
documented), so this depends on the official ``neo4j`` async driver
directly, as inventory and dashboard already do.
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
        max_records: int = 5_000,
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
                "Set AIIOS_NEO4J_HOST and AIIOS_KNOWLEDGE_GRAPH_SERVICE_NEO4J_ENABLED."
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

        A write clause fails here at the database. That is the guarantee
        behind custom Cypher; :mod:`app.cypher.guard` only makes the
        refusal legible.

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

        Only this service's own built-in statements reach here --
        never caller-authored Cypher, which has no path to this method.

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

    async def write_many(self, statements: list[tuple[str, dict[str, Any]]]) -> int:
        """Run several statements in **one** transaction; returns how many ran.

        One transaction rather than one per statement: a bulk import
        that fails halfway must not leave the graph holding half a
        payload, and the per-statement round trip is what makes a
        fifty-thousand-node import take minutes instead of hours.

        Raises:
            DependencyError: If the graph is unreachable or any
                statement fails -- in which case none of them applied.
        """
        driver = self._require_driver()
        if not statements:
            return 0
        try:
            async with driver.session(
                database=self._database, default_access_mode="WRITE"
            ) as session:
                transaction = await session.begin_transaction()
                try:
                    for cypher, parameters in statements:
                        await transaction.run(cypher, parameters)
                    await transaction.commit()
                except Exception:
                    await transaction.rollback()
                    raise
        except Exception as exc:
            logger.warning(
                "A batched graph write failed; nothing was applied.",
                extra={"extra_fields": {"statements": len(statements), "error": str(exc)}},
            )
            raise DependencyError(f"Graph write failed: {exc}") from exc
        return len(statements)

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
