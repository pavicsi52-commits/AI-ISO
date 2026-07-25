"""Secret audit trail.

Per docs/035 "AUDIT": Create, Update, Delete, Read, Decrypt, Rotate,
Lease, Export, Import, Provider Access, Administrative Operations.
**Zero plaintext persistence, absolutely no exception here** -- see
``app/models/secret_audit.py``'s own docstring; callers must never pass
a secret's plaintext or ciphertext into :attr:`before`/:attr:`after`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.secret_audit import SecretAuditEntry
from app.repositories.secret_audit import SecretAuditRepository


class SecretAuditService:
    """Records and lists privileged-action audit entries for a secret."""

    def __init__(self, audit: SecretAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        secret_id: UUID,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> SecretAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            SecretAuditEntry(
                secret_id=secret_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_secret(self, secret_id: UUID) -> list[SecretAuditEntry]:
        """Every audit entry for *secret_id*, newest first."""
        return await self._audit.list_for_secret(secret_id)


__all__ = ["SecretAuditService"]
