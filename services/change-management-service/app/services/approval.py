"""Requesting and deciding a change's approval chain.

Wraps ``app/approvals/engine.py`` with the database and the clock. The
engine decides whether a chain has resolved; this module decides what
to do once it has -- open CAB review if the change needs one, or leave
the change ready for ``ChangeService.schedule`` to pick up if not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.approvals.engine import ApprovalStep, active_level, chain_status, required_levels_for
from app.changes.engine import validate_transition
from app.events.change_events import SOURCE_SERVICE, ChangeApprovedEvent
from app.models.approval import ChangeApproval
from app.models.enums import (
    ApprovalPolicy,
    ApprovalStatus,
    ChangeStatus,
    approval_status_of,
    change_status_of,
    risk_level_of,
)
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.approval import ChangeApprovalRepository
from app.repositories.change import ChangeRequestRepository
from app.types import EventPublisher

logger = get_logger("app.services.approval")


class ApprovalService:
    """The approval chain: requesting it, deciding it, sweeping expiry."""

    def __init__(
        self,
        approvals: ChangeApprovalRepository,
        changes: ChangeRequestRepository,
        notifications: ChangeNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        minimum_approvals_high_risk: int = 2,
        default_expiry_hours: int = 72,
    ) -> None:
        self._approvals = approvals
        self._changes = changes
        self._notifications = notifications
        self._publish = publish_event
        self._minimum_approvals_high_risk = minimum_approvals_high_risk
        self._default_expiry_hours = default_expiry_hours

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def request_approvals(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        policy: ApprovalPolicy,
        approvers: list[tuple[str, str | None]],
        now: datetime | None = None,
    ) -> list[ChangeApproval]:
        """Open a change's approval chain.

        *approvers* is one ``(approver_id, approver_role)`` pair per
        required level, in level order -- the caller (an org's own RBAC
        and on-call data, which this service does not own) resolves who
        those people actually are; this only builds the chain.

        Raises:
            ConflictError: If the change is not ``PENDING_APPROVAL``, or
                fewer approvers were supplied than the policy requires.
        """
        moment = now or datetime.now(UTC)
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        if current is not ChangeStatus.PENDING_APPROVAL:
            raise ConflictError(
                f"{stored.reference} is {current!s}; approvals cannot be requested against it."
            )

        risk_level = risk_level_of(stored.risk_level) if stored.risk_level else None
        required = required_levels_for(
            policy=policy,
            risk_level=risk_level,
            minimum_approvals_high_risk=self._minimum_approvals_high_risk,
        )
        if len(approvers) < required:
            raise ConflictError(
                f"{policy!s} requires at least {required} approver(s); {len(approvers)} supplied."
            )

        expires_at = moment + timedelta(hours=self._default_expiry_hours)
        created: list[ChangeApproval] = []
        for level, (approver_id, approver_role) in enumerate(approvers, start=1):
            row = await self._approvals.create(
                ChangeApproval(
                    organization_id=organization_id,
                    change_id=change_id,
                    policy=policy,
                    level=level,
                    approver_id=approver_id,
                    approver_role=approver_role,
                    status=ApprovalStatus.PENDING,
                    expires_at=expires_at,
                )
            )
            created.append(row)

        first_level_approvers = [one for one in created if one.level == 1]
        for one in first_level_approvers:
            await self._notifications.send_approval_required(
                one.approver_id, reference=stored.reference, title=stored.title, level=1
            )
        return created

    async def decide(
        self,
        organization_id: UUID,
        approval_id: UUID,
        *,
        decision: ApprovalStatus,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> ChangeApproval:
        """Record one approver's decision, and advance the change once the chain resolves.

        Raises:
            ConflictError: If the step has already resolved.
        """
        moment = now or datetime.now(UTC)
        row = await self._approvals.require_in_org(organization_id, approval_id)
        if approval_status_of(row.status) is not ApprovalStatus.PENDING:
            raise ConflictError(f"Approval step {approval_id} is {row.status!s}, not pending.")

        row.status = decision
        row.comment = comment
        row.decided_at = moment
        await self._approvals.update(row)

        steps = await self._approvals.list_for_change(organization_id, row.change_id)
        outcome = chain_status(
            [
                ApprovalStep(
                    level=one.level,
                    approver_id=one.approver_id,
                    status=approval_status_of(one.status),
                )
                for one in steps
            ]
        )
        if outcome is ApprovalStatus.PENDING:
            await self._notify_next_level(organization_id, row.change_id, steps)
            return row

        stored = await self._changes.require_in_org(organization_id, row.change_id)
        if outcome is ApprovalStatus.REJECTED:
            validate_transition(change_status_of(stored.status), ChangeStatus.REJECTED)
            stored.status = ChangeStatus.REJECTED
            await self._changes.update(stored)
            return row

        # APPROVED or CONDITIONAL: the chain has resolved favourably.
        stored.approved_at = moment
        if stored.submitted_at is not None:
            stored.approval_duration_seconds = (moment - stored.submitted_at).total_seconds()
        if not stored.cab_required:
            await self._changes.update(stored)
        else:
            validate_transition(change_status_of(stored.status), ChangeStatus.CAB_REVIEW)
            stored.status = ChangeStatus.CAB_REVIEW
            await self._changes.update(stored)

        await self._publish_event(
            ChangeApprovedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "change_id": str(row.change_id),
                    "outcome": str(outcome),
                    "cab_required": stored.cab_required,
                },
            )
        )
        return row

    async def _notify_next_level(
        self, organization_id: UUID, change_id: UUID, steps: list[ChangeApproval]
    ) -> None:
        level = active_level(
            [
                ApprovalStep(
                    level=one.level,
                    approver_id=one.approver_id,
                    status=approval_status_of(one.status),
                )
                for one in steps
            ]
        )
        if level is None:
            return
        stored = await self._changes.require_in_org(organization_id, change_id)
        for one in steps:
            if one.level == level and approval_status_of(one.status) is ApprovalStatus.PENDING:
                await self._notifications.send_approval_required(
                    one.approver_id, reference=stored.reference, title=stored.title, level=level
                )

    async def delegate(
        self,
        organization_id: UUID,
        approval_id: UUID,
        *,
        delegated_to: str,
        now: datetime | None = None,
    ) -> ChangeApproval:
        """Reassign a pending approval step to someone else.

        The original step is closed out as ``DELEGATED``; a fresh
        ``PENDING`` step at the same level is opened for the delegate,
        so the level's own resolution rule (every step at a level must
        resolve) still has something concrete to resolve.

        Raises:
            ConflictError: If the step has already resolved.
        """
        moment = now or datetime.now(UTC)
        original = await self._approvals.require_in_org(organization_id, approval_id)
        if approval_status_of(original.status) is not ApprovalStatus.PENDING:
            raise ConflictError(f"Approval step {approval_id} is {original.status!s}, not pending.")

        original.status = ApprovalStatus.DELEGATED
        original.delegated_to = delegated_to
        original.decided_at = moment
        await self._approvals.update(original)

        return await self._approvals.create(
            ChangeApproval(
                organization_id=organization_id,
                change_id=original.change_id,
                policy=original.policy,
                level=original.level,
                approver_id=delegated_to,
                approver_role=original.approver_role,
                status=ApprovalStatus.PENDING,
                delegated_from=original.approver_id,
                expires_at=original.expires_at,
            )
        )

    async def sweep_expired(self, organization_id: UUID, *, now: datetime | None = None) -> int:
        """Mark every overdue pending approval step expired.

        Returns the count, for the worker to log. An expired step is
        left in place rather than auto-approved or auto-rejected -- an
        approval nobody acted on is a process failure to surface, not a
        decision this service is entitled to make on someone's behalf.
        """
        moment = now or datetime.now(UTC)
        expired = 0
        for row in await self._approvals.list_pending_expiring_before(
            organization_id, before=moment
        ):
            row.status = ApprovalStatus.EXPIRED
            await self._approvals.update(row)
            expired += 1
        return expired

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeApproval]:
        """Every approval step for one change, ordered by level."""
        return await self._approvals.list_for_change(organization_id, change_id)


__all__ = ["ApprovalService"]
