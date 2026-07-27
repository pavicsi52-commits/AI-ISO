"""Playbook tags. Per docs/041 "PLAYBOOK MODEL" "Tags"."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.playbook_tag import PlaybookTag
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_tag import PlaybookTagRepository


class PlaybookTagService:
    """Assigns, lists, and removes playbook tags."""

    def __init__(self, tags: PlaybookTagRepository, playbooks: PlaybookRepository) -> None:
        self._tags = tags
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookTag]:
        """Every tag assigned to *playbook_id*."""
        return await self._tags.list_for_playbook(playbook_id)

    async def add(self, playbook_id: UUID, *, tag: str) -> PlaybookTag:
        """Assign a new tag to a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
            ConflictError: If *tag* is already assigned to this playbook.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        existing = await self._tags.get_by_tag(playbook_id, tag)
        if existing is not None:
            raise ConflictError(f"Tag {tag!r} is already assigned to this playbook.")
        return await self._tags.create(
            PlaybookTag(organization_id=playbook.organization_id, playbook_id=playbook_id, tag=tag)
        )

    async def remove(self, tag_id: UUID) -> None:
        """Remove a tag assignment."""
        await self._tags.delete(tag_id)


__all__ = ["PlaybookTagService"]
