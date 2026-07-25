"""Credential sets -- named bundles of related secret ids. No REST
surface of its own -- exists for programmatic completeness, matching
``services/project-service``'s identical no-REST-surface sub-resource
services.
"""

from __future__ import annotations

from uuid import UUID

from app.models.credential_set import CredentialSet
from app.repositories.credential_set import CredentialSetRepository


class CredentialSetService:
    """Creates, lists, and edits credential-set membership."""

    def __init__(self, credential_sets: CredentialSetRepository) -> None:
        self._credential_sets = credential_sets

    async def list_for_org(self, organization_id: UUID) -> list[CredentialSet]:
        """Every credential set belonging to *organization_id*."""
        return await self._credential_sets.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        description: str | None = None,
        secret_ids: list[UUID] | None = None,
    ) -> CredentialSet:
        """Create a new credential set."""
        return await self._credential_sets.create(
            CredentialSet(
                organization_id=organization_id,
                name=name,
                description=description,
                secret_ids=[str(secret_id) for secret_id in (secret_ids or [])],
            )
        )

    async def add_secret(self, credential_set_id: UUID, secret_id: UUID) -> CredentialSet:
        """Add *secret_id* to a credential set, if not already present.

        Raises:
            NotFoundError: If no such credential set exists.
        """
        credential_set = await self._credential_sets.require_by_id(credential_set_id)
        if str(secret_id) not in credential_set.secret_ids:
            credential_set.secret_ids = [*credential_set.secret_ids, str(secret_id)]
        return credential_set

    async def remove_secret(self, credential_set_id: UUID, secret_id: UUID) -> CredentialSet:
        """Remove *secret_id* from a credential set, if present.

        Raises:
            NotFoundError: If no such credential set exists.
        """
        credential_set = await self._credential_sets.require_by_id(credential_set_id)
        credential_set.secret_ids = [
            existing for existing in credential_set.secret_ids if existing != str(secret_id)
        ]
        return credential_set

    async def delete(self, credential_set_id: UUID) -> None:
        """Delete a credential set.

        Raises:
            NotFoundError: If no such credential set exists.
        """
        await self._credential_sets.delete(credential_set_id)


__all__ = ["CredentialSetService"]
