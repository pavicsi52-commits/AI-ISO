"""GET/POST/DELETE /users/{user_id}/notes{,/{note_id}}.

Unlike every other self-scoped router in this package, notes are
admin/manager-authored *about* another user (docs/031's own "DATABASE
TABLES" list, not elaborated further) -- so this one genuinely needs
an explicit ``{user_id}`` path parameter; ``current_user_id`` is the
*author*, not the subject.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, NoteSvc
from app.models.note import UserNote
from app.schemas.note import NoteCreateRequest, NoteResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/{user_id}/notes", tags=["Notes"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(note: UserNote) -> NoteResponse:
    return NoteResponse(
        id=note.id, author_id=note.author_id, body=note.body, created_at=note.created_at
    )


@router.post("", response_model=SuccessResponse[NoteResponse], status_code=201)
async def add_note(
    user_id: UUID, body: NoteCreateRequest, notes: NoteSvc, current_user_id: CurrentUserId
) -> SuccessResponse[NoteResponse]:
    """Add an internal note about *user_id*, authored by the caller."""
    note = await notes.add(user_id, author_id=current_user_id, body=body.body)
    return SuccessResponse(message="Note added.", data=_to_response(note), meta=_meta())


@router.get("", response_model=SuccessResponse[list[NoteResponse]])
async def list_notes(
    user_id: UUID, notes: NoteSvc, _caller: CurrentUserId
) -> SuccessResponse[list[NoteResponse]]:
    """List every internal note on record about *user_id*."""
    records = await notes.list_for_user(user_id)
    return SuccessResponse(
        message="Notes retrieved.", data=[_to_response(n) for n in records], meta=_meta()
    )


@router.delete("/{note_id}", response_model=SuccessResponse[dict[str, bool]])
async def remove_note(
    user_id: UUID, note_id: UUID, notes: NoteSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Remove a note about *user_id*."""
    await notes.remove(user_id, note_id)
    return SuccessResponse(message="Note removed.", data={"success": True}, meta=_meta())


__all__ = ["router"]
