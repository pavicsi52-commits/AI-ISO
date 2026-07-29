"""HTTP routers for the knowledge graph service.

**Include order matters.** docs/049 specifies both ``/graph/nodes/{id}``
and literal collections like ``/graph/topology``, ``/graph/statistics``,
and ``/graph/query``. FastAPI matches routes in registration order, so
the routers owning literal segments must be included *before*
:data:`graph_router` -- otherwise ``/graph/topology`` would be parsed as
a node whose key is the word "topology".
"""

from __future__ import annotations

from app.api.admin import router as admin_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.query import router as query_router

__all__ = [
    "admin_router",
    "graph_router",
    "health_router",
    "query_router",
]
