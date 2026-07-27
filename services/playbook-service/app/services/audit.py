"""Playbook service audit trail.

Per docs/041 "AUDIT": Creation, Modification, Approval, Publishing,
Deletion, Version Changes, Signature Verification, Administrative
Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.playbook_audit import PlaybookAuditEntry
from app.repositories.playbook_audit import PlaybookAuditRepository


class PlaybookAuditService:
    """Records and lists privileged-action audit entries for playbooks."""

    def __init__(self, audit: PlaybookAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        *,
        playbook_id: UUID | None,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> PlaybookAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            PlaybookAuditEntry(
                playbook_id=playbook_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookAuditEntry]:
        """Every audit entry for *playbook_id*, newest first."""
        return await self._audit.list_for_playbook(playbook_id)


__all__ = ["PlaybookAuditService"]
