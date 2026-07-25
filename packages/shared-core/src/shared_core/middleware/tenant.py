"""Tenant resolution middleware.

Reads the organization/project headers per docs/006_API_Design_Master.md.txt
and binds them to the logging context and request state. Enforcement (that
a request may only access its own tenant's data) lives in
docs/017_Enterprise_Security_Framework.md.txt / docs/018 tenant isolation.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from shared_core.constants.http import HttpConstants
from shared_core.logging.context import bind_log_context


class TenantResolutionMiddleware:
    """ASGI middleware resolving organization/project context from headers."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        organization_id = request.headers.get(HttpConstants.HEADER_ORGANIZATION_ID)
        project_id = request.headers.get(HttpConstants.HEADER_PROJECT_ID)

        bind_log_context(organization_id=organization_id, project_id=project_id)
        scope["state"] = scope.get("state", {})
        scope["state"]["organization_id"] = organization_id
        scope["state"]["project_id"] = project_id

        await self._app(scope, receive, send)
