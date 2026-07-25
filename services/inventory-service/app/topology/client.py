"""Neo4j driver lifecycle.

Per docs/036 "TOPOLOGY": "Integrate with Neo4j." No ``shared_core``
driver wrapper exists (confirmed by reuse research: ``shared_core``
only provides ``Neo4jSettings``/``Neo4jConstants`` config plumbing and
a generic TCP-reachability health check, the same "no dedicated client
wrapper yet" gap its own ``monitoring/checks.py`` documents for
Neo4j/OpenSearch/SMTP) -- this service is the first in the platform to
actually talk to Neo4j, so it depends on the official ``neo4j`` async
driver directly, the same "add the one missing library to this
service's own pyproject.toml" precedent ``openpyxl``/``reportlab``
already established for Excel/PDF support.
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
