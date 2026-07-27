"""Playbook auxiliary script files, per docs/041 "SUPPORTED CONTENT"
(Python/PowerShell/Shell/Bash Scripts).
"""

from __future__ import annotations

from uuid import UUID

from app.models.enums import ContentType
from app.models.playbook_script import PlaybookScript
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_script import PlaybookScriptRepository


class PlaybookScriptService:
    """Creates, reads, and deletes playbook auxiliary script files."""

    def __init__(self, scripts: PlaybookScriptRepository, playbooks: PlaybookRepository) -> None:
        self._scripts = scripts
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookScript]:
        """Every auxiliary script file bundled with *playbook_id*."""
        return await self._scripts.list_for_playbook(playbook_id)

    async def create(
        self,
        playbook_id: UUID,
        *,
        file_name: str,
        script_type: ContentType,
        content: str,
        is_entry_point: bool,
    ) -> PlaybookScript:
        """Bundle a new auxiliary script file with a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._scripts.create(
            PlaybookScript(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                file_name=file_name,
                script_type=script_type,
                content=content,
                is_entry_point=is_entry_point,
            )
        )

    async def delete(self, script_id: UUID) -> None:
        """Remove an auxiliary script file."""
        await self._scripts.delete(script_id)


__all__ = ["PlaybookScriptService"]
