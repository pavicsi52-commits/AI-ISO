"""Project note management -- no dedicated REST surface in docs/034's
own endpoint list, matching ``app/services/preferences.py``'s identical
scope decision.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.project_note import ProjectNote
from app.repositories.project_note import ProjectNoteRepository


class ProjectNoteService:
    """Creates, lists, updates, and removes free-form notes on a project."""

    def __init__(self, notes: ProjectNoteRepository) -> None:
        self._notes = notes

    async def list_for_project(self, project_id: UUID) -> list[ProjectNote]:
        """Every note on *project_id*, pinned first."""
        return await self._notes.list_for_project(project_id)

    async def create(
        self,
        project_id: UUID,
        *,
        organization_id: UUID,
        author_id: UUID,
        title: str | None,
        content: str,
        is_pinned: bool = False,
    ) -> ProjectNote:
        """Add a note to *project_id*."""
        return await self._notes.create(
            ProjectNote(
                project_id=project_id,
                organization_id=organization_id,
                author_id=author_id,
                title=title,
                content=content,
                is_pinned=is_pinned,
            )
        )

    async def remove(self, project_id: UUID, note_id: UUID) -> None:
        """Remove a note.

        Raises:
            NotFoundError: If no such note exists for *project_id*.
        """
        record = await self._notes.require_by_id(note_id)
        if record.project_id != project_id:
            raise NotFoundError(f"Note '{note_id}' was not found for this project.")
        await self._notes.delete(note_id)


__all__ = ["ProjectNoteService"]
