"""Playbook Ansible role references, per docs/041 "SUPPORTED CONTENT"
"Ansible Roles".
"""

from __future__ import annotations

from uuid import UUID

from app.models.playbook_role import PlaybookRole
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_role import PlaybookRoleRepository


class PlaybookRoleService:
    """Creates, reads, and deletes playbook Ansible role references."""

    def __init__(self, roles: PlaybookRoleRepository, playbooks: PlaybookRepository) -> None:
        self._roles = roles
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRole]:
        """Every Ansible role *playbook_id* references."""
        return await self._roles.list_for_playbook(playbook_id)

    async def create(
        self,
        playbook_id: UUID,
        *,
        role_name: str,
        role_source: str,
        role_version: str | None,
    ) -> PlaybookRole:
        """Declare a new Ansible role reference for a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._roles.create(
            PlaybookRole(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                role_name=role_name,
                role_source=role_source,
                role_version=role_version,
            )
        )

    async def delete(self, role_id: UUID) -> None:
        """Remove an Ansible role reference."""
        await self._roles.delete(role_id)


__all__ = ["PlaybookRoleService"]
