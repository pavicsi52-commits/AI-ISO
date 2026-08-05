"""The reverse-proxy catch-all -- the gateway's core feature.

Registered dead last in the app factory (``app/core/factory.py``), mirroring
notification-center-service's own hard-learned router-ordering lesson: a
route matching every path and method would otherwise swallow this
service's own management endpoints (``/health``, every ``/gateway/*``
route, ``/docs``) if it were registered before them.

Route resolution happens twice per call -- once here, to enforce the
resolved route's own auth requirements before any upstream call is
attempted, and once more inside :meth:`ProxyService.proxy`, which needs
its own resolved route to log and forward against. Both resolve the same
in-memory route list from the same request-scoped session; the duplicate
query is a deliberate, cheap trade against threading a pre-resolved route
through the service boundary.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from shared_core.enums.permission import Permission
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.not_found import NotFoundError

from app.api.deps import AuthSvc, ProxySvc, RouteSvc
from app.models.enums import AuthenticationMethod
from app.services.auth import AuthContext
from app.services.proxy import ProxyError

router = APIRouter(tags=["Proxy"])

_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "upgrade",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "host",
    }
)


async def _authenticate(request: Request, auth: AuthSvc, api_key: str | None) -> AuthContext:
    """Authenticate via API key, then Bearer JWT, then fall back to anonymous."""
    if api_key:
        source_ip = request.client.host if request.client else None
        return await auth.authenticate_api_key(api_key, source_ip=source_ip)
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return await auth.authenticate_jwt(authorization[len("bearer ") :])
    return auth.authenticate_anonymous()


def _forward_headers(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    summary="Reverse-proxy any request to a registered backend service",
    include_in_schema=False,
)
async def proxy_request(
    full_path: str,
    request: Request,
    proxy: ProxySvc,
    auth: AuthSvc,
    routes: RouteSvc,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_organization_id: Annotated[UUID | None, Header(alias="X-Organization-Id")] = None,
) -> Response:
    """Resolve, authenticate, authorize, and forward one external request.

    Raises:
        AuthenticationError: If no organization can be resolved for the
            call, the route requires authentication the caller did not
            present, or the caller's authentication method is not one
            the resolved route accepts.
        AuthorizationError: If the caller is authenticated but lacks the
            resolved route's required scopes or permission.
        NotFoundError: If no configured route matches this request.
    """
    context = await _authenticate(request, auth, x_api_key)
    organization_id = context.organization_id or x_organization_id
    if organization_id is None:
        raise AuthenticationError("No organization could be resolved for this request.")

    path = f"/{full_path}"
    resolved_route = await routes.resolve(
        organization_id, method=request.method, path=path, headers=dict(request.headers)
    )
    if resolved_route is None:
        raise NotFoundError("No route matches this request.")

    if resolved_route.requires_auth and context.method == AuthenticationMethod.ANONYMOUS:
        raise AuthenticationError("This route requires authentication.")
    if (
        resolved_route.allowed_auth_methods
        and context.method.value not in resolved_route.allowed_auth_methods
    ):
        raise AuthenticationError(
            f"This route does not accept {context.method.value!r} authentication."
        )

    decision = auth.authorize_request(
        context,
        target_organization_id=organization_id,
        required_permission=(
            Permission(resolved_route.required_permission)
            if resolved_route.required_permission
            else None
        ),
        required_scopes=resolved_route.required_scopes or None,
    )
    if not decision.granted:
        raise AuthorizationError(decision.reason)

    body = await request.body()
    try:
        result = await proxy.proxy(
            organization_id,
            method=request.method,
            path=path,
            query_string=str(request.url.query) or None,
            headers=_forward_headers(request),
            body=body,
            source_ip=request.client.host if request.client else None,
            client_id=context.client_id,
            api_key_id=(
                UUID(context.subject_id)
                if context.method == AuthenticationMethod.API_KEY and context.subject_id
                else None
            ),
            authenticated_user_id=context.subject_id,
            auth_method=context.method,
        )
    except ProxyError as exc:
        return Response(
            content=exc.detail.encode("utf-8"), status_code=exc.status_code, media_type="text/plain"
        )

    response_headers = {
        k: v for k, v in result.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(content=result.body, status_code=result.status_code, headers=response_headers)


__all__ = ["router"]
