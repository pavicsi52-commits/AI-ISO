"""Dashboard audit trail ("AUDIT").

Per docs/048: Dashboard Created/Updated/Deleted/Viewed, Widget
Added/Updated/Removed, Layout Changed, Share Created/Revoked,
Permission Changed, Theme Changed, Template Created/Applied.

**Denials are audited, not just successes.** An attempt to open a
dashboard the caller had no right to is precisely what a security
reviewer is looking for, and a trail that records only what worked
cannot show it.

**Auditing never fails the audited action.** Writes go through
:meth:`AuditService.record`, which logs and swallows storage failures.
That is a deliberate trade for this service: a dashboard is what an
operator stares at during an incident, and refusing to render one
because an audit insert hit a deadlock would turn a bookkeeping problem
into an operational one. Services with a regulatory retention duty --
``secrets-management`` and ``compliance`` -- make the opposite choice
and let the write fail loudly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.models.dashboard_audit import DashboardAudit
from app.models.enums import AuditAction, AuditOutcome
from app.repositories.dashboard_audit import DashboardAuditRepository

logger = get_logger("app.services.audit")


def action_of(entry: DashboardAudit) -> AuditAction:
    """An entry's action as a genuine enum member.

    ``action`` is annotated ``Mapped[AuditAction]`` but stored in a
    ``String``, so a row loaded from Postgres yields a raw ``str``.
    """
    value = entry.action
    return value if isinstance(value, AuditAction) else AuditAction(value)


def outcome_of(entry: DashboardAudit) -> AuditOutcome:
    """An entry's outcome as a genuine enum member."""
    value = entry.outcome
    return value if isinstance(value, AuditOutcome) else AuditOutcome(value)


class AuditService:
    """Writes and reads the dashboard audit trail."""

    def __init__(self, audits: DashboardAuditRepository) -> None:
        self._audits = audits

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
    ) -> DashboardAudit | None:
        """Append one audit entry, best-effort.

        Returns the stored entry, or ``None`` if it could not be
        written -- see this module's docstring for why that is not
        raised.
        """
        try:
            return await self._audits.create(
                DashboardAudit(
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
        except Exception as exc:
            logger.error(
                "Failed to write a dashboard audit entry; the audited action still stands.",
                extra={
                    "extra_fields": {
                        "action": str(action),
                        "entity_type": entity_type,
                        "entity_id": str(entity_id) if entity_id else None,
                        "error": str(exc),
                    }
                },
            )
            return None

    async def record_denied(
        self,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        entity_id: UUID | None,
        actor_id: UUID | None,
        reason: str,
    ) -> DashboardAudit | None:
        """Append a ``DENIED`` entry for a refused action."""
        return await self.record(
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            outcome=AuditOutcome.DENIED,
            reason=reason,
        )

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[DashboardAudit]:
        """Audit entries for one organization, most recent first."""
        return await self._audits.list_for_org(organization_id, action=action, limit=limit)

    async def list_for_entity(self, entity_id: UUID, *, limit: int = 100) -> list[DashboardAudit]:
        """Everything audited against one entity, most recent first."""
        return await self._audits.list_for_entity(entity_id, limit=limit)

    async def summarise(self, organization_id: UUID, *, limit: int = 1_000) -> dict[str, Any]:
        """Counts per action and per outcome.

        Both normalised through :func:`action_of` and :func:`outcome_of`:
        the rows come back from Postgres as strings, and a summary keyed
        by a mix of enum members and strings would double-count.
        """
        entries = await self._audits.list_for_org(organization_id, limit=limit)
        by_action: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        for entry in entries:
            action = str(action_of(entry))
            outcome = str(outcome_of(entry))
            by_action[action] = by_action.get(action, 0) + 1
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        return {
            "total": len(entries),
            "by_action": by_action,
            "by_outcome": by_outcome,
            "denied": by_outcome.get(str(AuditOutcome.DENIED), 0),
        }


__all__ = ["AuditService", "action_of", "outcome_of"]
