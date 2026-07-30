"""Violations, exceptions, and the audit trail.

Three things that go together: what broke a rule, what was excused, and
the record of both.

**Every exception expires.** The API cannot create one without an
expiry, and the service refuses an unreasonably long one. A permanent
exception is not an exception -- it is an undocumented policy change
that no review will surface, because it does not look like one.

**The audit trail is append-only.** Nothing here updates a row. For the
service that authorizes every protected operation on the platform, a
mutable trail would be worth less than none -- it would look
authoritative while being editable by whoever the trail is about.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.database.session import session_scope
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.policy_events import SOURCE_SERVICE, PolicyViolationDetectedEvent
from app.models.decision import PolicyException, PolicyViolation
from app.models.enums import (
    AuditAction,
    AuditOutcome,
    ComplianceStandard,
    ResourceType,
    SubjectType,
    ViolationStatus,
)
from app.models.operations import PolicyAudit
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.runtime import (
    PolicyAuditRepository,
    PolicyExceptionRepository,
    PolicyViolationRepository,
)
from app.types import EventPublisher

logger = get_logger("app.services.compliance")

MAX_EXCEPTION_DAYS = 90
"""The longest a waiver may run.

Bounded because an exception is the mechanism by which a policy stops
applying, and the whole reason it is acceptable is that it comes back.
Ninety days is long enough for a genuine remediation project and short
enough that it will be looked at again.
"""

_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})


def status_of(record: PolicyViolation) -> ViolationStatus:
    """A violation's status as a genuine enum member."""
    value = record.status
    return value if isinstance(value, ViolationStatus) else ViolationStatus(value)


def standard_of(record: PolicyViolation) -> ComplianceStandard:
    """A violation's standard as a genuine enum member."""
    value = record.standard
    return value if isinstance(value, ComplianceStandard) else ComplianceStandard(value)


def action_of(entry: PolicyAudit) -> AuditAction:
    """An audit entry's action as a genuine enum member."""
    value = entry.action
    return value if isinstance(value, AuditAction) else AuditAction(value)


def outcome_of(entry: PolicyAudit) -> AuditOutcome:
    """An audit entry's outcome as a genuine enum member."""
    value = entry.outcome
    return value if isinstance(value, AuditOutcome) else AuditOutcome(value)


class ComplianceService:
    """Records violations and manages exceptions."""

    def __init__(
        self,
        violations: PolicyViolationRepository,
        exceptions: PolicyExceptionRepository,
        notifications: PolicyNotificationService,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._violations = violations
        self._exceptions = exceptions
        self._notifications = notifications
        self._publish_event = publish_event

    async def record_violation(
        self,
        organization_id: UUID,
        *,
        title: str,
        standard: ComplianceStandard,
        severity: str = "medium",
        description: str | None = None,
        policy_id: UUID | None = None,
        decision_id: UUID | None = None,
        subject_type: SubjectType = SubjectType.USER,
        subject_id: str | None = None,
        resource_type: ResourceType = ResourceType.CUSTOM_RESOURCE,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        notify_user_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyViolation:
        """Record a broken rule and announce it.

        Raises:
            ValidationError: If the severity is not one of the four
                bands. A free-text severity makes "show me the critical
                ones" unanswerable.
        """
        if severity not in _SEVERITIES:
            permitted = ", ".join(sorted(_SEVERITIES))
            raise ValidationError(f"{severity!r} is not a severity. Permitted: {permitted}.")

        stored = await self._violations.create(
            PolicyViolation(
                organization_id=organization_id,
                policy_id=policy_id,
                decision_id=decision_id,
                title=title,
                description=description,
                standard=standard,
                severity=severity,
                subject_type=subject_type,
                subject_id=subject_id,
                resource_type=resource_type,
                resource_id=resource_id,
                status=ViolationStatus.OPEN,
                details=details or {},
                detected_at=datetime.now(UTC),
                created_by=actor_id,
            )
        )

        await self._publish_event(
            PolicyViolationDetectedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "violation_id": str(stored.id),
                    "title": title,
                    "severity": severity,
                    "standard": str(standard),
                },
            )
        )
        if notify_user_id:
            await self._notifications.send_violation(
                notify_user_id,
                title=title,
                severity=severity,
                detail=description or title,
            )
        return stored

    async def acknowledge(
        self,
        organization_id: UUID,
        violation_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> PolicyViolation:
        """Mark a violation as seen.

        A distinct state from resolved, and worth having: "somebody knows
        about this" and "this is fixed" are different facts, and
        collapsing them means an acknowledged-but-unfixed violation
        disappears from the list of things to do.

        Raises:
            ConflictError: If it is already resolved or waived.
        """
        stored = await self._violations.require_in_org(organization_id, violation_id)
        current = status_of(stored)
        if current in (ViolationStatus.RESOLVED, ViolationStatus.WAIVED):
            raise ConflictError(
                f"This violation is already {current!s} and cannot be acknowledged."
            )
        stored.status = ViolationStatus.ACKNOWLEDGED
        stored.acknowledged_at = datetime.now(UTC)
        stored.acknowledged_by = actor_id
        stored.updated_by = actor_id
        return await self._violations.update(stored)

    async def resolve(
        self,
        organization_id: UUID,
        violation_id: UUID,
        *,
        note: str,
        waived: bool = False,
        actor_id: UUID | None = None,
    ) -> PolicyViolation:
        """Close a violation, either fixed or explicitly waived.

        The note is required, and for waivers especially: a violation
        closed without a stated reason is indistinguishable from one
        somebody clicked past.

        Raises:
            ValidationError: If no note is given.
        """
        if not note.strip():
            raise ValidationError(
                "Closing a violation needs a note saying what was done. Without one "
                "nobody reviewing this later can tell it apart from a dismissal."
            )
        stored = await self._violations.require_in_org(organization_id, violation_id)
        stored.status = ViolationStatus.WAIVED if waived else ViolationStatus.RESOLVED
        stored.resolved_at = datetime.now(UTC)
        stored.resolved_by = actor_id
        stored.resolution_note = note
        stored.updated_by = actor_id
        return await self._violations.update(stored)

    async def list_violations(
        self,
        organization_id: UUID,
        *,
        status: ViolationStatus | None = None,
        severity: str | None = None,
        limit: int = 200,
    ) -> list[PolicyViolation]:
        """Violations, most recent first."""
        return await self._violations.list_for_org(
            organization_id, status=status, severity=severity, limit=limit
        )

    # ---- exceptions -----------------------------------------------------

    async def grant_exception(
        self,
        organization_id: UUID,
        *,
        policy_id: UUID,
        reason: str,
        expires_at: datetime,
        subject_type: SubjectType | None = None,
        subject_id: str | None = None,
        resource_type: ResourceType | None = None,
        resource_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyException:
        """Waive one policy, for a bounded time and a bounded scope.

        Raises:
            ValidationError: If the reason is empty, the expiry is in the
                past, or it runs longer than
                :data:`MAX_EXCEPTION_DAYS`.
        """
        if not reason.strip():
            raise ValidationError(
                "An exception needs a stated reason. Without one it is "
                "indistinguishable from a mistake when somebody reviews it later."
            )

        now = datetime.now(UTC)
        deadline = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if deadline <= now:
            raise ValidationError(
                f"An exception must expire in the future, got {deadline.isoformat()}."
            )
        if deadline > now + timedelta(days=MAX_EXCEPTION_DAYS):
            raise ValidationError(
                f"An exception may run at most {MAX_EXCEPTION_DAYS} days. A longer "
                "waiver is a policy change; make it one so it gets reviewed as one."
            )

        stored = await self._exceptions.create(
            PolicyException(
                organization_id=organization_id,
                policy_id=policy_id,
                reason=reason,
                subject_type=subject_type,
                subject_id=subject_id,
                resource_type=resource_type,
                resource_id=resource_id,
                granted_by=actor_id,
                granted_at=now,
                expires_at=deadline,
                created_by=actor_id,
            )
        )
        logger.warning(
            "A policy exception was granted; the policy is waived for its scope until it expires.",
            extra={
                "extra_fields": {
                    "organization_id": str(organization_id),
                    "policy_id": str(policy_id),
                    "exception_id": str(stored.id),
                    "expires_at": deadline.isoformat(),
                    "reason": reason,
                }
            },
        )
        return stored

    async def revoke_exception(
        self,
        organization_id: UUID,
        exception_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> PolicyException:
        """End a waiver early.

        Raises:
            NotFoundError: If it does not exist here.
            ConflictError: If it has already been revoked.
        """
        stored = await self._exceptions.require_by_id(exception_id)
        if stored.organization_id != organization_id:
            raise NotFoundError(f"No exception with id {exception_id} in this organization.")
        if stored.revoked_at is not None:
            raise ConflictError("This exception has already been revoked.")
        stored.revoked_at = datetime.now(UTC)
        stored.revoked_by = actor_id
        stored.updated_by = actor_id
        return await self._exceptions.update(stored)

    async def list_exceptions(
        self, organization_id: UUID, *, active_only: bool = False, limit: int = 200
    ) -> list[PolicyException]:
        """Waivers, newest first."""
        if active_only:
            return await self._exceptions.list_active(organization_id, moment=datetime.now(UTC))
        return await self._exceptions.list_for_org(organization_id, limit=limit)

    async def overused_exceptions(
        self, organization_id: UUID, *, threshold: int = 100
    ) -> list[PolicyException]:
        """Waivers relied on so often they have become the real policy.

        The number that makes a quiet problem visible: a waiver used a
        thousand times is not an exception, and nothing else in the system
        would ever say so.
        """
        rows = await self._exceptions.list_for_org(organization_id, limit=500)
        return [one for one in rows if one.use_count >= threshold]


class AuditService:
    """Writes and reads the append-only policy audit trail."""

    def __init__(
        self,
        audits: PolicyAuditRepository,
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
        entity_id: str | None = None,
        actor_id: UUID | None = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        reason: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyAudit | None:
        """Append one entry, best-effort.

        Returns ``None`` if it could not be written. Refusing to answer
        an authorization question because an audit insert hit a deadlock
        would turn a bookkeeping problem into a platform-wide outage --
        this service is in front of every protected operation.
        """
        return await self._record_on(
            self._audits,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            outcome=outcome,
            reason=reason,
            before=before,
            after=after,
            context=context,
        )

    async def record_denied(
        self,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        reason: str,
        entity_id: str | None = None,
        actor_id: UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyAudit | None:
        """Append a ``DENIED`` entry, in its own transaction.

        **Committed independently**, unlike every other write here, and
        that is the whole reason this method exists separately. A refusal
        is recorded and then *raised* -- and the raise rolls the request's
        transaction back, taking any entry written inside it. The lesson
        came from ``services/knowledge-graph-service``, where a
        DENIED-audit test passed for as long as the behaviour was broken
        because a request-scoped SAVEPOINT does not roll back the way a
        real request does.
        """
        if self._session_factory is None:
            return await self._record_on(
                self._audits,
                organization_id=organization_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                outcome=AuditOutcome.DENIED,
                reason=reason,
                context=context,
            )

        try:
            async with session_scope(self._session_factory) as session:
                return await self._record_on(
                    PolicyAuditRepository(session),
                    organization_id=organization_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
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

    @staticmethod
    async def _record_on(
        audits: PolicyAuditRepository,
        *,
        organization_id: UUID,
        action: AuditAction,
        entity_type: str,
        entity_id: str | None,
        actor_id: UUID | None,
        outcome: AuditOutcome,
        reason: str | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PolicyAudit | None:
        """Append one entry through a given repository, best-effort."""
        try:
            return await audits.create(
                PolicyAudit(
                    organization_id=organization_id,
                    action=action,
                    outcome=outcome,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    actor_id=actor_id,
                    reason=reason,
                    before=before,
                    after=after,
                    context=context or {},
                    occurred_at=datetime.now(UTC),
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to write a policy audit entry; the audited action still stands.",
                extra={
                    "extra_fields": {
                        "action": str(action),
                        "entity_type": entity_type,
                        "error": str(exc),
                    }
                },
            )
            return None

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[PolicyAudit]:
        """Audit entries, most recent first."""
        return await self._audits.list_for_org(organization_id, action=action, limit=limit)

    async def list_for_entity(
        self, organization_id: UUID, entity_id: str, *, limit: int = 100
    ) -> list[PolicyAudit]:
        """Everything audited against one entity."""
        return await self._audits.list_for_entity(organization_id, entity_id, limit=limit)

    async def summarise(self, organization_id: UUID, *, limit: int = 1_000) -> dict[str, Any]:
        """Counts per action and per outcome.

        Both normalised, because rows come back from Postgres as strings
        and a summary keyed on a mix of enum members and strings would
        double-count.
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


__all__ = [
    "MAX_EXCEPTION_DAYS",
    "AuditService",
    "ComplianceService",
    "action_of",
    "outcome_of",
    "standard_of",
    "status_of",
]
