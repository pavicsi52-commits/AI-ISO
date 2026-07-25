"""Configuration management audit trail.

Per docs/039 "AUDIT": Configuration Creation, Updates, Version Changes,
Assignments, Approvals, Drift Detection, Compliance Results, Rollback,
Restore, Administrative Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.configuration_audit import ConfigurationAuditEntry
from app.models.enums import AuditOutcome
from app.repositories.configuration_audit import ConfigurationAuditRepository


class ConfigurationAuditService:
    """Records and lists privileged-action audit entries for a configuration profile."""

    def __init__(self, audit: ConfigurationAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        profile_id: UUID | None,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> ConfigurationAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            ConfigurationAuditEntry(
                profile_id=profile_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationAuditEntry]:
        """Every audit entry for *profile_id*, newest first."""
        return await self._audit.list_for_profile(profile_id)


__all__ = ["ConfigurationAuditService"]
