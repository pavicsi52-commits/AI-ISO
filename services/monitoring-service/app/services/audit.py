"""Administrative audit trail. Per docs/044 "AUDIT": Collector
Configuration, Threshold Changes, Rule Changes, Synthetic Test Changes,
Retention Policy Updates, Administrative Operations.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import AuditOutcome
from app.models.monitoring_audit import MonitoringAuditEntry
from app.repositories.monitoring_audit import MonitoringAuditEntryRepository


class MonitoringAuditService:
    """Records and reads monitoring administrative audit entries."""

    def __init__(self, entries: MonitoringAuditEntryRepository) -> None:
        self._entries = entries

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringAuditEntry]:
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
    ) -> MonitoringAuditEntry:
        """Record one privileged/administrative action."""
        return await self._entries.create(
            MonitoringAuditEntry(
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


__all__ = ["MonitoringAuditService"]
