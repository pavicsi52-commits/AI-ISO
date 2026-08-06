"""API client registration -- a supporting surface docs/056's own "AUTHENTICATION"/
"API KEY MANAGEMENT" sections need to be operable (an API key must belong to a
client), matching the "extend the literal API list with the routes its own
feature section requires" precedent every prior AI-IOS service already establishes.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import ClientSvc, CurrentUserId
from app.schemas.gateway import ClientCreateRequest, ClientResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/clients", tags=["Clients"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ClientResponse]], summary="List API clients")
async def list_clients(
    organization_id: UUID, clients: ClientSvc
) -> SuccessResponse[list[ClientResponse]]:
    """Every client registered in this organization."""
    rows = await clients.list_clients(organization_id)
    return SuccessResponse(
        message="Clients listed.",
        data=[ClientResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{client_id}", response_model=SuccessResponse[ClientResponse], summary="Get an API client"
)
async def get_client(
    organization_id: UUID, client_id: UUID, clients: ClientSvc
) -> SuccessResponse[ClientResponse]:
    """One client."""
    found = await clients.get(organization_id, client_id)
    return SuccessResponse(
        message="Client found.", data=ClientResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[ClientResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register an API client",
)
async def create_client(
    organization_id: UUID, body: ClientCreateRequest, clients: ClientSvc, caller: CurrentUserId
) -> SuccessResponse[ClientResponse]:
    """Register a new API consumer."""
    created = await clients.register(
        organization_id,
        name=body.name,
        client_kind=body.client_kind,
        description=body.description,
        contact_email=body.contact_email,
        actor_id=str(caller),
    )
    return SuccessResponse(
        message="Client registered.", data=ClientResponse.model_validate(created), meta=_meta()
    )


__all__ = ["router"]
