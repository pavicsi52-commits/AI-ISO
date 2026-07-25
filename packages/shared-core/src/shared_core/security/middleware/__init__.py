"""Security-specific ASGI middleware: JWT validation, session validation.

Per docs/017_Enterprise_Security_Framework.md.txt "SECURITY MIDDLEWARE":
security headers, rate limiting, and request/correlation ID middleware
already exist in :mod:`shared_core.middleware` (Prompt 012) and are not
duplicated here -- only JWT and session validation, which need this
package's own JWT/session logic, are new.
"""

from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from shared_core.enums.role import Role
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.context import bind_security_context, reset_security_context
from shared_core.security.jwt import decode_token
from shared_core.security.sessions import SessionManager


class JwtAuthenticationMiddleware:
    """ASGI middleware verifying a Bearer JWT and binding :class:`SecurityContext`.

    A missing/invalid token is not itself rejected here -- many routes
    are public. Only when a token is present is it verified; a route that
    requires authentication uses ``@requires_auth`` (or another
    ``@requires_*`` decorator) to enforce that a context was actually bound.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        public_key: str,
        role_claim: str = "role",
        organization_claim: str = "organization_id",
        project_claim: str = "project_id",
    ) -> None:
        self._app = app
        self._public_key = public_key
        self._role_claim = role_claim
        self._organization_claim = organization_claim
        self._project_claim = project_claim

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            self._bind_from_token(authorization.removeprefix("Bearer "))

        try:
            await self._app(scope, receive, send)
        finally:
            reset_security_context()

    def _bind_from_token(self, token: str) -> None:
        try:
            claims = decode_token(token, public_key=self._public_key)
        except AuthenticationError:
            return

        role_value = claims.get(self._role_claim)
        organization_id = claims.get(self._organization_claim)
        project_id = claims.get(self._project_claim)
        bind_security_context(
            user_id=UUID(claims["sub"]) if claims.get("sub") else None,
            role=Role(role_value) if role_value else None,
            organization_id=UUID(organization_id) if organization_id else None,
            project_id=UUID(project_id) if project_id else None,
            auth_method="jwt",
        )


class SessionValidationMiddleware:
    """ASGI middleware validating a session cookie against a :class:`SessionManager`."""

    def __init__(
        self, app: ASGIApp, *, session_manager: SessionManager, cookie_name: str = "session_id"
    ) -> None:
        self._app = app
        self._session_manager = session_manager
        self._cookie_name = cookie_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        session_id = request.cookies.get(self._cookie_name)
        if session_id:
            session = await self._session_manager.validate_session(session_id)
            if session is not None:
                scope["state"] = scope.get("state", {})
                scope["state"]["session"] = session

        await self._app(scope, receive, send)
