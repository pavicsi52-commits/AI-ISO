"""Playbook variables. Per docs/041 "VARIABLES" "Support"."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.playbook_variable import PlaybookVariable
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_variable import PlaybookVariableRepository


class PlaybookVariableService:
    """Creates, reads, and deletes playbook input-variable definitions."""

    def __init__(
        self, variables: PlaybookVariableRepository, playbooks: PlaybookRepository
    ) -> None:
        self._variables = variables
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookVariable]:
        """Every variable definition for *playbook_id*."""
        return await self._variables.list_for_playbook(playbook_id)

    async def create(
        self,
        playbook_id: UUID,
        *,
        name: str,
        default_value: str | None,
        required: bool,
        runtime: bool,
        is_secret_reference: bool,
        env_var_name: str | None,
        validation_rule: dict[str, Any] | None,
        description: str | None,
    ) -> PlaybookVariable:
        """Define a new input-variable for a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._variables.create(
            PlaybookVariable(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                name=name,
                default_value=default_value,
                required=required,
                runtime=runtime,
                is_secret_reference=is_secret_reference,
                env_var_name=env_var_name,
                validation_rule=validation_rule,
                description=description,
            )
        )

    async def delete(self, variable_id: UUID) -> None:
        """Soft-delete a variable definition."""
        await self._variables.delete(variable_id)


__all__ = ["PlaybookVariableService"]
