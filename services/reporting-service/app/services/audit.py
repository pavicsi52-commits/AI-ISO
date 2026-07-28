"""Reporting audit ("AUDIT").

Append-only: nothing here updates or deletes an entry. ``DENIED`` is a
first-class outcome, because an attempt to export a report the caller
had no right to is exactly what an auditor most wants to see -- and a
service that only records successes cannot answer that question.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.enums import AuditAction, AuditOutcome
from app.models.report_audit import ReportAudit
from app.repositories.report_audit import ReportAuditRepository


class ReportAuditService:
    """Records and reads reporting audit entries."""

    def __init__(self, entries: ReportAuditRepository) -> None:
        self._entries = entries

    async def record(
        self,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
        project_id: UUID | None = None,
    ) -> ReportAudit:
        """Append one audit entry."""
        return await self._entries.create(
            ReportAudit(
                organization_id=organization_id,
                project_id=project_id,
                action=action,
                outcome=outcome,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                reason=reason,
                context=context or {},
                occurred_at=datetime.now(UTC),
            )
        )

    async def list_for_org(
        self, organization_id: UUID, *, action: AuditAction | None = None, limit: int = 200
    ) -> list[ReportAudit]:
        """Audit entries for an organization, most recent first."""
        return await self._entries.list_for_org(organization_id, action=action, limit=limit)

    async def list_for_entity(self, entity_id: UUID, *, limit: int = 100) -> list[ReportAudit]:
        """Everything audited against one entity."""
        return await self._entries.list_for_entity(entity_id, limit=limit)


__all__ = ["ReportAuditService"]
