"""Playbook labels. Per docs/041 "PLAYBOOK MODEL" "Labels"."""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.playbook_label import PlaybookLabel
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_label import PlaybookLabelRepository


class PlaybookLabelService:
    """Assigns, lists, and removes playbook labels."""

    def __init__(self, labels: PlaybookLabelRepository, playbooks: PlaybookRepository) -> None:
        self._labels = labels
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookLabel]:
        """Every label assigned to *playbook_id*."""
        return await self._labels.list_for_playbook(playbook_id)

    async def add(self, playbook_id: UUID, *, key: str, value: str) -> PlaybookLabel:
        """Assign a new key/value label to a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
            ConflictError: If *key* is already assigned to this playbook.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        existing = await self._labels.get_by_key(playbook_id, key)
        if existing is not None:
            raise ConflictError(f"Label {key!r} is already assigned to this playbook.")
        return await self._labels.create(
            PlaybookLabel(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                key=key,
                value=value,
            )
        )

    async def remove(self, label_id: UUID) -> None:
        """Remove a label assignment."""
        await self._labels.delete(label_id)


__all__ = ["PlaybookLabelService"]
