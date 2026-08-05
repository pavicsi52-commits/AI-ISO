"""GraphQL mount, at ``/graphql``."""

from __future__ import annotations

from typing import Any

from strawberry.fastapi import GraphQLRouter

from app.api.deps import DbSession, get_route_service, get_service_registry, get_statistics_service
from app.graphql.schema import schema


async def get_graphql_context(session: DbSession) -> dict[str, Any]:
    """Build the per-request context GraphQL resolvers read from.

    ``session`` resolves through the same ``get_db_session`` dependency
    every REST route uses -- strawberry's FastAPI integration wraps this
    function as a dependency itself, so nested ``Depends`` resolve
    exactly as they would in an ordinary route.
    """
    return {
        "session": session,
        "services": get_service_registry(session),
        "routes": get_route_service(session),
        "statistics": get_statistics_service(session),
    }


router = GraphQLRouter(schema, context_getter=get_graphql_context, path="/graphql")

__all__ = ["router"]
