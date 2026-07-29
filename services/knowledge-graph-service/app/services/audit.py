"""Graph audit trail ("AUDIT").

Per docs/049: node changes, relationship changes, synchronization,
imports, exports, graph queries, and administrative operations.

**A refused Cypher statement is audited as ``DENIED``**, and that is the
entry this trail exists for. Someone probing ``POST /graph/cypher`` with
``DETACH DELETE`` produces no state change and would leave no trace at
all in a trail that recorded only successes -- which is exactly the
event a security reviewer is looking for.

**Auditing never fails the audited action.** Writes go through
:meth:`AuditService.record`, which logs and swallows storage failures.
That is the right trade here for the same reason it was in
``services/dashboard-service``: refusing to answer a topology query
because an audit insert hit a deadlock turns a bookkeeping problem into
an operational one during an incident. Services with a regulatory
retention duty -- ``secrets-management``, ``compliance`` -- make the
opposite choice deliberately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.models.enums import AuditAction, AuditOutcome
from app.models.graph_audit import GraphAudit
from app.repositories.graph_audit import GraphAuditRepository

logger = get_logger("app.services.audit")


def action_of(entry: GraphAudit) -> AuditAction:
    """An entry's action as a genuine enum member.

    ``action`` is annotated ``Mapped[AuditAction]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = entry.action
    return value if isinstance(value, AuditAction) else AuditAction(value)


def outcome_of(entry: GraphAudit) -> AuditOutcome:
    """An entry's outcome as a genuine enum member."""
    value = entry.outcome
    return value if isinstance(value, AuditOutcome) else AuditOutcome(value)


class AuditService:
    """Writes and reads the knowledge-graph audit trail."""

    def __init__(self, audits: GraphAuditRepository) -> None:
        self._audits = audits

    async def record(
        self,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        entity_key: str | None = None,
        actor_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
        project_id: UUID | None = None,
    ) -> GraphAudit | None:
        """Append one audit entry, best-effort.

        Returns the stored entry, or ``None`` if it could not be written
        -- see this module's docstring for why that is not raised.
        """
        try:
            return await self._audits.create(
                GraphAudit(
                    organization_id=organization_id,
                    project_id=project_id,
                    action=action,
                    outcome=outcome,
                    entity_type=entity_type,
                    entity_key=entity_key,
                    actor_id=actor_id,
                    reason=reason,
                    context=context or {},
                    occurred_at=datetime.now(UTC),
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to write a graph audit entry; the audited action still stands.",
                extra={
                    "extra_fields": {
                        "action": str(action),
                        "entity_type": entity_type,
                        "entity_key": entity_key,
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
        reason: str,
        entity_key: str | None = None,
        actor_id: UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> GraphAudit | None:
        """Append a ``DENIED`` entry for a refused action."""
        return await self.record(
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_key=entity_key,
            actor_id=actor_id,
            outcome=AuditOutcome.DENIED,
            reason=reason,
            context=context,
        )

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[GraphAudit]:
        """Audit entries for one organization, most recent first."""
        return await self._audits.list_for_org(organization_id, action=action, limit=limit)

    async def list_for_entity(self, entity_key: str, *, limit: int = 100) -> list[GraphAudit]:
        """Everything audited against one entity, most recent first."""
        return await self._audits.list_for_entity(entity_key, limit=limit)

    async def summarise(self, organization_id: UUID, *, limit: int = 1_000) -> dict[str, Any]:
        """Counts per action and per outcome.

        Both normalised through :func:`action_of` and :func:`outcome_of`:
        rows come back from Postgres as strings, and a summary keyed by a
        mix of enum members and strings would double-count.
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
