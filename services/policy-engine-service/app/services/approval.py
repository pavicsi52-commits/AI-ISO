"""Approvals as a service: raise an obligation, collect answers, resolve.

The arithmetic lives in :mod:`app.approvals.engine`; this is the storage
and notification side.

**An approval is raised by a decision, not by a caller.** A
``REQUIRE_APPROVAL`` effect produces a pending row automatically, because
an obligation nobody can see is an obligation nobody will satisfy -- the
caller would simply be refused with no route forward.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.approvals import engine as approvals
from app.events.policy_events import SOURCE_SERVICE, PolicyApprovedEvent
from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    ResourceType,
    SubjectType,
)
from app.models.governance import PolicyApproval
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.runtime import PolicyApprovalRepository
from app.types import EventPublisher

logger = get_logger("app.services.approval")


def status_of(record: PolicyApproval) -> ApprovalStatus:
    """An approval's status as a genuine enum member.

    ``status`` is annotated ``Mapped[ApprovalStatus]`` but stored in a
    ``String``, so a row loaded from Postgres yields a plain ``str``.
    """
    value = record.status
    return value if isinstance(value, ApprovalStatus) else ApprovalStatus(value)


def type_of(record: PolicyApproval) -> ApprovalType:
    """An approval's type as a genuine enum member."""
    value = record.approval_type
    return value if isinstance(value, ApprovalType) else ApprovalType(value)


class ApprovalService:
    """Raises, resolves, and sweeps approval obligations."""

    def __init__(
        self,
        approvals_repository: PolicyApprovalRepository,
        notifications: PolicyNotificationService,
        *,
        publish_event: EventPublisher,
        expiry_hours: int = 48,
        emergency_enabled: bool = True,
    ) -> None:
        self._approvals = approvals_repository
        self._notifications = notifications
        self._publish_event = publish_event
        self._expiry_hours = expiry_hours
        self._emergency_enabled = emergency_enabled

    async def raise_for_decision(
        self,
        organization_id: UUID,
        *,
        policy_id: UUID | None,
        decision_id: UUID | None,
        subject_type: SubjectType,
        subject_id: str,
        resource_type: ResourceType,
        resource_id: str | None,
        action: ActionType,
        obligations: dict[str, Any],
        risk_score: float = 0.0,
        context: dict[str, Any] | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyApproval:
        """Create the pending obligation a REQUIRE_APPROVAL decision implies."""
        declared_type = ApprovalType(str(obligations.get("approval_type") or ApprovalType.SINGLE))
        if declared_type is ApprovalType.EMERGENCY and not self._emergency_enabled:
            raise ConflictError(
                "Emergency (break-glass) approvals are disabled on this deployment."
            )

        required = approvals.required_levels(
            declared_type,
            declared=int(obligations.get("levels") or 1),
            risk_score=risk_score,
        )
        expires_at = approvals.expiry_for(
            declared_type, hours=self._expiry_hours, now=datetime.now(UTC)
        )

        stored = await self._approvals.create(
            PolicyApproval(
                organization_id=organization_id,
                policy_id=policy_id,
                decision_id=decision_id,
                approval_type=declared_type,
                status=ApprovalStatus.PENDING,
                subject_type=subject_type,
                subject_id=subject_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                required_levels=required,
                required_roles=list(obligations.get("required_roles") or []),
                decisions=[],
                requested_at=datetime.now(UTC),
                requested_by=actor_id,
                expires_at=expires_at,
                reason=str(obligations.get("reason") or ""),
                is_emergency=declared_type is ApprovalType.EMERGENCY,
                context_snapshot=context or {},
                created_by=actor_id,
            )
        )

        await self._notifications.send_approval_required(
            subject_id,
            resource=f"{resource_type}:{resource_id or '*'}",
            action=str(action),
            expires_at=expires_at.isoformat(),
        )
        if stored.is_emergency:
            # Break-glass is always announced. What makes it acceptable
            # to have at all is that nobody can use it quietly.
            logger.warning(
                "An emergency (break-glass) approval was raised.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "approval_id": str(stored.id),
                        "subject_id": subject_id,
                        "resource": f"{resource_type}:{resource_id or '*'}",
                        "action": str(action),
                    }
                },
            )
        return stored

    async def record_decision(
        self,
        organization_id: UUID,
        approval_id: UUID,
        *,
        approver_id: str,
        approved: bool,
        comment: str = "",
        approver_roles: list[str] | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyApproval:
        """Record one approver's answer and re-resolve the obligation.

        Raises:
            ConflictError: If the approval is no longer pending.
            ValidationError: If this approver may not answer.
        """
        stored = await self._approvals.require_in_org(organization_id, approval_id)
        current = status_of(stored)
        if current is not ApprovalStatus.PENDING:
            raise ConflictError(
                f"This approval is already {current!s} and cannot be changed. "
                "Raise a new request if the situation has changed."
            )

        existing = [approvals.decision_from_dict(one) for one in (stored.decisions or [])]
        approvals.validate_approver(
            approver_id,
            decisions=existing,
            required_roles=list(stored.required_roles or []),
            approver_roles=approver_roles or [],
            requested_by=stored.requested_by,
            # Break-glass is the one case where the requester may sign
            # off, because there is genuinely nobody else at 03:00. It is
            # flagged, logged, and notified precisely so that this
            # exemption is never invisible.
            allow_self_approval=stored.is_emergency,
        )

        answer = approvals.ApproverDecision(
            approver_id=approver_id,
            approved=approved,
            decided_at=datetime.now(UTC),
            comment=comment,
            roles=tuple(approver_roles or ()),
        )
        recorded = [*existing, answer]
        state = approvals.resolve(
            recorded,
            required=stored.required_levels,
            expires_at=stored.expires_at,
            now=datetime.now(UTC),
        )

        stored.decisions = [one.as_dict() for one in recorded]
        stored.status = state.status
        stored.updated_by = actor_id
        if state.status is not ApprovalStatus.PENDING:
            stored.resolved_at = datetime.now(UTC)
        updated = await self._approvals.update(stored)

        if state.status is ApprovalStatus.APPROVED:
            await self._publish_event(
                PolicyApprovedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "approval_id": str(approval_id),
                        "subject_id": stored.subject_id,
                        "approvals": state.approvals,
                        "emergency": stored.is_emergency,
                    },
                )
            )
        return updated

    async def cancel(
        self,
        organization_id: UUID,
        approval_id: UUID,
        *,
        reason: str,
        actor_id: UUID | None = None,
    ) -> PolicyApproval:
        """Withdraw a pending approval.

        Raises:
            ConflictError: If it has already been resolved.
        """
        stored = await self._approvals.require_in_org(organization_id, approval_id)
        if status_of(stored) is not ApprovalStatus.PENDING:
            raise ConflictError(
                f"This approval is already {status_of(stored)!s} and cannot be cancelled."
            )
        stored.status = ApprovalStatus.CANCELLED
        stored.resolved_at = datetime.now(UTC)
        stored.reason = reason
        stored.updated_by = actor_id
        return await self._approvals.update(stored)

    async def sweep_expired(self, organization_id: UUID) -> int:
        """Mark overdue pending approvals as expired; returns how many.

        Swept rather than left pending, because a pending approval is an
        actionable item on somebody's list. One that can never complete
        sitting there forever is how a queue stops being read at all.
        """
        moment = datetime.now(UTC)
        overdue = await self._approvals.list_expired_pending(organization_id, moment=moment)
        for stored in overdue:
            stored.status = ApprovalStatus.EXPIRED
            stored.resolved_at = moment
            await self._approvals.update(stored)
        if overdue:
            logger.info(
                "Expired overdue approval requests.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "expired": len(overdue),
                    }
                },
            )
        return len(overdue)

    async def get(self, organization_id: UUID, approval_id: UUID) -> PolicyApproval:
        """One approval.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        return await self._approvals.require_in_org(organization_id, approval_id)

    async def state_of(self, organization_id: UUID, approval_id: UUID) -> approvals.ApprovalState:
        """Re-derive where an approval stands, from its recorded answers.

        Derived rather than read off the status column, so a row whose
        deadline passed since it was last written reports as expired
        without waiting for the sweep.
        """
        stored = await self._approvals.require_in_org(organization_id, approval_id)
        return approvals.resolve(
            [approvals.decision_from_dict(one) for one in (stored.decisions or [])],
            required=stored.required_levels,
            expires_at=stored.expires_at,
            now=datetime.now(UTC),
        )

    async def list_approvals(
        self,
        organization_id: UUID,
        *,
        status: ApprovalStatus | None = None,
        subject_id: str | None = None,
        limit: int = 200,
    ) -> list[PolicyApproval]:
        """Approvals, most recently requested first."""
        return await self._approvals.list_for_org(
            organization_id, status=status, subject_id=subject_id, limit=limit
        )

    async def validate_obligations(self, obligations: dict[str, Any]) -> None:
        """Check an approval obligation before a policy carrying it is published.

        Raises:
            ValidationError: If it names an unknown approval type or an
                impossible level count. Caught at publish time, because
                the alternative is a policy that refuses requests and
                then cannot raise the obligation that would let them
                through -- a dead end with no route forward.
        """
        declared = obligations.get("approval_type")
        if declared is not None:
            try:
                ApprovalType(str(declared))
            except ValueError as exc:
                permitted = ", ".join(sorted(str(one) for one in ApprovalType))
                raise ValidationError(
                    f"{declared!r} is not an approval type. Permitted: {permitted}."
                ) from exc

        levels = obligations.get("levels")
        if levels is not None and (not isinstance(levels, int) or levels < 1):
            raise ValidationError(f"An approval needs at least one level, got {levels!r}.")


__all__ = ["ApprovalService", "status_of", "type_of"]
