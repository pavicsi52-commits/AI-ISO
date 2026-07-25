"""Inventory audit trail.

Per docs/036 "AUDIT": Asset Creation, Updates, Deletion, Imports,
Exports, Relationship Changes, Ownership Changes, Status Changes,
Metadata Changes, Administrative Actions. **Zero plaintext/sensitive
persistence concern here** (unlike
``services/secrets-management-service``'s own audit trail) since this
service handles no secret material -- ``before``/``after`` may safely
capture full field snapshots.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.inventory_audit import InventoryAuditEntry
from app.repositories.inventory_audit import InventoryAuditRepository


class InventoryAuditService:
    """Records and lists privileged-action audit entries for an asset."""

    def __init__(self, audit: InventoryAuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        asset_id: UUID | None,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> InventoryAuditEntry:
        """Record one privileged/administrative action."""
        return await self._audit.create(
            InventoryAuditEntry(
                asset_id=asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                reason=reason,
                before=before,
                after=after,
            )
        )

    async def list_for_asset(self, asset_id: UUID) -> list[InventoryAuditEntry]:
        """Every audit entry for *asset_id*, newest first."""
        return await self._audit.list_for_asset(asset_id)


__all__ = ["InventoryAuditService"]
