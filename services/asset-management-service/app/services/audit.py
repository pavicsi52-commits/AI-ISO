"""Asset management audit trail.

Per docs/038 "AUDIT": Ownership Changes, Assignments, Maintenance,
Compliance Changes, Risk Updates, Lifecycle Events, Financial Updates,
Administrative Operations. **Zero plaintext/sensitive persistence
concern here** (unlike ``services/secrets-management-service``'s own
audit trail) since this service handles no secret material --
``before``/``after`` may safely capture full field snapshots.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.asset_audit import AssetAuditEntry
from app.models.enums import AuditOutcome
from app.repositories.asset_audit import AssetAuditRepository


class AssetAuditService:
    """Records and lists privileged-action audit entries for a managed asset."""

    def __init__(self, audit: AssetAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        managed_asset_id: UUID | None,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AssetAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            AssetAuditEntry(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetAuditEntry]:
        """Every audit entry for *managed_asset_id*, newest first."""
        return await self._audit.list_for_managed_asset(managed_asset_id)


__all__ = ["AssetAuditService"]
