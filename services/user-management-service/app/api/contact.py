"""GET/POST/DELETE /users/contacts{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ContactSvc, CurrentUserId
from app.models.contact import UserContact
from app.schemas.contact import ContactCreateRequest, ContactResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/contacts", tags=["Contacts"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(contact: UserContact) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        contact_type=contact.contact_type,
        value=contact.value,
        label=contact.label,
        is_primary=contact.is_primary,
        is_verified=contact.is_verified,
    )


@router.post("", response_model=SuccessResponse[ContactResponse], status_code=201)
async def add_contact(
    body: ContactCreateRequest, contacts: ContactSvc, current_user_id: CurrentUserId
) -> SuccessResponse[ContactResponse]:
    """Add a new contact method for the caller."""
    contact = await contacts.add(
        current_user_id,
        contact_type=body.contact_type,
        value=body.value,
        label=body.label,
        is_primary=body.is_primary,
    )
    return SuccessResponse(message="Contact added.", data=_to_response(contact), meta=_meta())


@router.get("", response_model=SuccessResponse[list[ContactResponse]])
async def list_contacts(
    contacts: ContactSvc, current_user_id: CurrentUserId
) -> SuccessResponse[list[ContactResponse]]:
    """List the caller's own additional contact methods."""
    records = await contacts.list_for_user(current_user_id)
    return SuccessResponse(
        message="Contacts retrieved.", data=[_to_response(c) for c in records], meta=_meta()
    )


@router.delete("/{contact_id}", response_model=SuccessResponse[dict[str, bool]])
async def remove_contact(
    contact_id: UUID, contacts: ContactSvc, current_user_id: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Remove one of the caller's own contact methods."""
    await contacts.remove(current_user_id, contact_id)
    return SuccessResponse(message="Contact removed.", data={"success": True}, meta=_meta())


__all__ = ["router"]
