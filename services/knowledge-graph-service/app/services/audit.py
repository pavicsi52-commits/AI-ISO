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

from shared_core.database.session import session_scope
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    def __init__(
        self,
        audits: GraphAuditRepository,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._audits = audits
        self._session_factory = session_factory

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
        return await self._record_on(
            self._audits,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_key=entity_key,
            actor_id=actor_id,
            outcome=outcome,
            reason=reason,
            context=context,
            project_id=project_id,
        )

    @staticmethod
    async def _record_on(
        audits: GraphAuditRepository,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        entity_key: str | None,
        actor_id: UUID | None,
        outcome: AuditOutcome,
        reason: str | None,
        context: dict[str, Any] | None,
        project_id: UUID | None = None,
    ) -> GraphAudit | None:
        """Append one entry through a given repository, best-effort."""
        try:
            return await audits.create(
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
        """Append a ``DENIED`` entry for a refused action.

        **Committed in its own transaction**, unlike every other write
        here, and that is the whole reason this method exists separately.
        A refusal is recorded and then the refusal is *raised* -- which
        rolls the request's transaction back and takes any entry written
        inside it with it. The trail that exists specifically to record
        somebody probing ``POST /graph/cypher`` recorded nothing at all
        until a live container was asked for it: a request-scoped
        SAVEPOINT in a test never rolls back the way a real request does,
        so the test passed.
        """
        if self._session_factory is None:
            # No independent factory (a unit test, or a caller that owns
            # its own transaction boundary). Recorded on the shared
            # session, which is better than not recorded.
            return await self._record_on(
                self._audits,
                organization_id=organization_id,
                action=action,
                entity_type=entity_type,
                entity_key=entity_key,
                actor_id=actor_id,
                outcome=AuditOutcome.DENIED,
                reason=reason,
                context=context,
            )

        try:
            async with session_scope(self._session_factory) as session:
                return await self._record_on(
                    GraphAuditRepository(session),
                    organization_id=organization_id,
                    action=action,
                    entity_type=entity_type,
                    entity_key=entity_key,
                    actor_id=actor_id,
                    outcome=AuditOutcome.DENIED,
                    reason=reason,
                    context=context,
                )
        except Exception as exc:
            logger.error(
                "Failed to write a DENIED audit entry in its own transaction.",
                extra={"extra_fields": {"action": str(action), "error": str(exc)}},
            )
            return None

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[GraphAudit]:
        """Audit entries for one organization, most recent first."""
        return await self._audits.list_for_org(organization_id, action=action, limit=limit)

    async def list_for_entity(
        self, organization_id: UUID, entity_key: str, *, limit: int = 100
    ) -> list[GraphAudit]:
        """Everything audited against one entity, most recent first."""
        return await self._audits.list_for_entity(organization_id, entity_key, limit=limit)

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
