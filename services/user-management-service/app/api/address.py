"""GET/POST/DELETE /users/addresses{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AddressSvc, CurrentUserId
from app.models.address import UserAddress
from app.schemas.address import AddressCreateRequest, AddressResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/addresses", tags=["Addresses"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(address: UserAddress) -> AddressResponse:
    return AddressResponse(
        id=address.id,
        address_type=address.address_type,
        line1=address.line1,
        line2=address.line2,
        city=address.city,
        state_province=address.state_province,
        postal_code=address.postal_code,
        country=address.country,
        is_primary=address.is_primary,
    )


@router.post("", response_model=SuccessResponse[AddressResponse], status_code=201)
async def add_address(
    body: AddressCreateRequest, addresses: AddressSvc, current_user_id: CurrentUserId
) -> SuccessResponse[AddressResponse]:
    """Add a new address for the caller."""
    address = await addresses.add(
        current_user_id,
        address_type=body.address_type,
        line1=body.line1,
        line2=body.line2,
        city=body.city,
        state_province=body.state_province,
        postal_code=body.postal_code,
        country=body.country,
        is_primary=body.is_primary,
    )
    return SuccessResponse(message="Address added.", data=_to_response(address), meta=_meta())


@router.get("", response_model=SuccessResponse[list[AddressResponse]])
async def list_addresses(
    addresses: AddressSvc, current_user_id: CurrentUserId
) -> SuccessResponse[list[AddressResponse]]:
    """List the caller's own addresses."""
    records = await addresses.list_for_user(current_user_id)
    return SuccessResponse(
        message="Addresses retrieved.", data=[_to_response(a) for a in records], meta=_meta()
    )


@router.delete("/{address_id}", response_model=SuccessResponse[dict[str, bool]])
async def remove_address(
    address_id: UUID, addresses: AddressSvc, current_user_id: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Remove one of the caller's own addresses."""
    await addresses.remove(current_user_id, address_id)
    return SuccessResponse(message="Address removed.", data={"success": True}, meta=_meta())


__all__ = ["router"]
