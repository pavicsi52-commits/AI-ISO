"""Administrative audit trail. Per docs/043 "AUDIT": Validation
Creation, Execution, Rule Changes, Profile Changes, Result
Modifications, Administrative Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.validation_audit import ValidationAuditEntry
from app.repositories.validation_audit import ValidationAuditEntryRepository


class ValidationAuditService:
    """Records and reads validation administrative audit entries."""

    def __init__(self, entries: ValidationAuditEntryRepository) -> None:
        self._entries = entries

    async def list_for_org(self, organization_id: UUID) -> list[ValidationAuditEntry]:
        """Every audit entry recorded for *organization_id*."""
        return await self._entries.list_for_org(organization_id)

    async def record(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> ValidationAuditEntry:
        """Record one privileged/administrative action."""
        return await self._entries.create(
            ValidationAuditEntry(
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                outcome=outcome,
                reason=reason,
                details=details,
            )
        )


__all__ = ["ValidationAuditService"]
