"""Neo4j driver lifecycle.

Per docs/048 "TOPOLOGY VISUALIZATION": "Integrate with Prompt 036."
That prompt's own ``services/inventory-service`` owns the graph and
established that ``shared_core`` provides only ``Neo4jSettings`` and a
TCP-reachability check, not a driver wrapper -- so this service depends
on the official ``neo4j`` async driver directly, exactly as inventory
does.

**Building the driver never fails startup.** A dashboard deployment
with no graph should still serve every non-topology dashboard; the
reader reports itself disabled and the resolver turns that into one
failed *widget* rather than a failed service.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase
from shared_core.config.settings import Neo4jSettings
from shared_core.logging.logger import get_logger

logger = get_logger("app.topology.client")


def create_neo4j_driver(settings: Neo4jSettings, *, enabled: bool = True) -> AsyncDriver | None:
    """Build an :class:`~neo4j.AsyncDriver`, or ``None`` when unavailable.

    The caller owns the driver's lifetime -- call
    :meth:`~neo4j.AsyncDriver.close` at shutdown, the same "one client,
    built once at startup, closed at shutdown" shape every other AI-IOS
    infrastructure client uses.
    """
    if not enabled:
        return None
    try:
        return AsyncGraphDatabase.driver(
            settings.uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    except Exception as exc:
        logger.warning(
            "Neo4j is unavailable; topology widgets will report themselves failed "
            "and every other widget type is unaffected.",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return None


__all__ = ["create_neo4j_driver"]
