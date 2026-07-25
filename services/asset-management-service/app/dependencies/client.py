"""Neo4j driver lifecycle.

Per docs/038 "DEPENDENCY ANALYSIS": "Integrate with Neo4j." No
``shared_core`` driver wrapper exists (the same gap ``services/
inventory-service``'s own ``app/topology/client.py`` documents), so
this service depends on the official ``neo4j`` async driver directly,
identically to that precedent.
"""

from __future__ import annotations

from neo4j import AsyncDriver, AsyncGraphDatabase
from shared_core.config.settings import Neo4jSettings


def create_neo4j_driver(settings: Neo4jSettings) -> AsyncDriver:
    """Build an :class:`~neo4j.AsyncDriver` bound to *settings*.

    The caller owns the driver's lifetime -- call
    :meth:`~neo4j.AsyncDriver.close` (or ``async with``) when done, the
    same "one client, built once at startup, closed at shutdown" shape
    every other AI-IOS infrastructure client in this codebase uses.
    """
    return AsyncGraphDatabase.driver(
        settings.uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


__all__ = ["create_neo4j_driver"]
