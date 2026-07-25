"""Secret tags ("SECRET MODEL": Tags). No REST surface of its own --
exists for programmatic completeness, matching
``services/project-service``'s identical no-REST-surface sub-resource
services.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.secret_tag import SecretTag
from app.repositories.secret_tag import SecretTagRepository


class SecretTagService:
    """Assigns, lists, and removes tags on a secret."""

    def __init__(self, tags: SecretTagRepository) -> None:
        self._tags = tags

    async def list_for_secret(self, secret_id: UUID) -> list[SecretTag]:
        """Every tag assigned to *secret_id*."""
        return await self._tags.list_for_secret(secret_id)

    async def assign(self, secret_id: UUID, *, organization_id: UUID, label: str) -> SecretTag:
        """Assign *label* to *secret_id*.

        Raises:
            ConflictError: If *label* is already assigned.
        """
        if await self._tags.get_by_label(secret_id, label) is not None:
            raise ConflictError(f"Tag {label!r} is already assigned to this secret.")
        return await self._tags.create(
            SecretTag(secret_id=secret_id, organization_id=organization_id, label=label)
        )

    async def remove(self, secret_id: UUID, tag_id: UUID) -> None:
        """Remove a tag.

        Raises:
            NotFoundError: If no such tag exists for *secret_id*.
        """
        record = await self._tags.require_by_id(tag_id)
        if record.secret_id != secret_id:
            raise NotFoundError(f"Tag '{tag_id}' was not found for this secret.")
        await self._tags.delete(tag_id)


__all__ = ["SecretTagService"]
