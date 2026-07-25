"""Secret metadata entries ("SECRET MODEL": Metadata). No REST surface
of its own -- exists for programmatic completeness, matching
``services/project-service``'s identical no-REST-surface sub-resource
services (see ``tests/test_services_no_rest_surface.py``).
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.secret_metadata import SecretMetadataEntry
from app.repositories.secret_metadata import SecretMetadataRepository


class SecretMetadataService:
    """Sets, lists, and removes metadata entries on a secret."""

    def __init__(self, metadata: SecretMetadataRepository) -> None:
        self._metadata = metadata

    async def list_for_secret(self, secret_id: UUID) -> list[SecretMetadataEntry]:
        """Every metadata entry for *secret_id*."""
        return await self._metadata.list_for_secret(secret_id)

    async def set(
        self, secret_id: UUID, *, organization_id: UUID, key: str, value: str
    ) -> SecretMetadataEntry:
        """Set *key* to *value* on *secret_id*.

        Raises:
            ConflictError: If *key* already exists (use :meth:`update` to change it).
        """
        if await self._metadata.get_by_key(secret_id, key) is not None:
            raise ConflictError(f"Metadata key {key!r} already exists on this secret.")
        return await self._metadata.create(
            SecretMetadataEntry(
                secret_id=secret_id, organization_id=organization_id, key=key, value=value
            )
        )

    async def remove(self, secret_id: UUID, entry_id: UUID) -> None:
        """Remove a metadata entry.

        Raises:
            NotFoundError: If no such entry exists for *secret_id*.
        """
        entry = await self._metadata.require_by_id(entry_id)
        if entry.secret_id != secret_id:
            raise NotFoundError(f"Metadata entry '{entry_id}' was not found for this secret.")
        await self._metadata.delete(entry_id)


__all__ = ["SecretMetadataService"]
