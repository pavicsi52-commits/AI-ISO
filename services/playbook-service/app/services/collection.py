"""Playbook Ansible collection references, per docs/041 "SUPPORTED
CONTENT" "Ansible Collections".
"""

from __future__ import annotations

from uuid import UUID

from app.models.playbook_collection import PlaybookCollection
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_collection import PlaybookCollectionRepository


class PlaybookCollectionService:
    """Creates, reads, and deletes playbook Ansible collection references."""

    def __init__(
        self, collections: PlaybookCollectionRepository, playbooks: PlaybookRepository
    ) -> None:
        self._collections = collections
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookCollection]:
        """Every Ansible collection *playbook_id* references."""
        return await self._collections.list_for_playbook(playbook_id)

    async def create(
        self,
        playbook_id: UUID,
        *,
        collection_name: str,
        collection_version: str | None,
        source: str | None,
    ) -> PlaybookCollection:
        """Declare a new Ansible collection reference for a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._collections.create(
            PlaybookCollection(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                collection_name=collection_name,
                collection_version=collection_version,
                source=source,
            )
        )

    async def delete(self, collection_id: UUID) -> None:
        """Remove an Ansible collection reference."""
        await self._collections.delete(collection_id)


__all__ = ["PlaybookCollectionService"]
