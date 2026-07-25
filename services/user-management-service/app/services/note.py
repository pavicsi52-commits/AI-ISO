"""Internal user note management. Per docs/031 "DATABASE TABLES": ``user_notes``."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.note import UserNote
from app.repositories.note import UserNoteRepository


class UserNoteService:
    """Creates, lists, and removes internal notes about a user."""

    def __init__(self, notes: UserNoteRepository) -> None:
        self._notes = notes

    async def add(self, user_id: UUID, *, author_id: UUID, body: str) -> UserNote:
        """Add a new note about *user_id*, authored by *author_id*."""
        return await self._notes.create(
            UserNote(
                user_id=user_id,
                author_id=author_id,
                body=body,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def list_for_user(self, user_id: UUID) -> list[UserNote]:
        """Every note on record about *user_id*, newest first."""
        return await self._notes.list_for_user(user_id)

    async def remove(self, user_id: UUID, note_id: UUID) -> None:
        """Remove a note about *user_id*.

        Raises:
            NotFoundError: If no such note about *user_id* exists.
        """
        record = await self._notes.require_by_id(note_id)
        if record.user_id != user_id:
            raise NotFoundError(f"Note '{note_id}' was not found.")
        await self._notes.delete(note_id)


__all__ = ["UserNoteService"]
