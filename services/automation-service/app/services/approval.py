"""Approval-workflow gates against pending automation executions.

Per docs/040 "APPROVALS" "Support": Single Approval, Multi-Level
Approval, Conditional Approval, Role-Based Approval, Approval
Expiration, Approval History, Emergency Override.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.automation_events import ApprovalGrantedEvent, ApprovalRequestedEvent
from app.models.automation_approval import AutomationApproval
from app.models.enums import ApprovalStatus, ApprovalType
from app.repositories.automation_approval import AutomationApprovalRepository
from app.repositories.automation_execution import AutomationExecutionRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class AutomationApprovalService:
    """Requests and decides automation approval-workflow steps."""

    def __init__(
        self,
        approvals: AutomationApprovalRepository,
        executions: AutomationExecutionRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._approvals = approvals
        self._executions = executions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, approval_id: UUID) -> AutomationApproval:
        """Return the approval step identified by *approval_id*.

        Raises:
            NotFoundError: If no such approval step exists.
        """
        return await self._approvals.require_by_id(approval_id)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationApproval]:
        """Every approval step recorded for *execution_id* ("Approval History")."""
        return await self._approvals.list_for_execution(execution_id)

    async def list_pending_for_org(self, organization_id: UUID) -> list[AutomationApproval]:
        """Every still-pending approval for *organization_id*."""
        return await self._approvals.list_pending_for_org(organization_id)

    async def request(
        self,
        execution_id: UUID,
        *,
        approval_type: ApprovalType,
        level: int,
        requested_by: UUID | None,
        expires_at: datetime | None,
    ) -> AutomationApproval:
        """Request a new approval-workflow gate ("Multi-Level Approval"),
        publishing ``ApprovalRequested``.

        Raises:
            NotFoundError: If *execution_id* does not exist.
        """
        execution = await self._executions.require_by_id(execution_id)
        approval = await self._approvals.create(
            AutomationApproval(
                organization_id=execution.organization_id,
                execution_id=execution_id,
                approval_type=approval_type,
                status=ApprovalStatus.PENDING,
                level=level,
                requested_by=requested_by,
                expires_at=expires_at,
            )
        )
        await self._publish(
            ApprovalRequestedEvent(
                source_service="automation-service",
                payload={"approval_id": str(approval.id), "execution_id": str(execution_id)},
            )
        )
        return approval

    async def decide(
        self,
        approval_id: UUID,
        *,
        status: ApprovalStatus,
        approver_id: UUID | None,
        comments: str | None,
    ) -> AutomationApproval:
        """Approve or reject an approval gate ("Emergency Override" is
        simply a decision at any level), publishing ``ApprovalGranted``
        on approval.
        """
        approval = await self.get_by_id(approval_id)
        approval.status = status
        approval.approver_id = approver_id
        approval.comments = comments
        approval.decided_at = datetime.now(UTC)
        approval = await self._approvals.update(approval)

        if status is ApprovalStatus.APPROVED:
            await self._publish(
                ApprovalGrantedEvent(
                    source_service="automation-service",
                    payload={
                        "approval_id": str(approval.id),
                        "execution_id": str(approval.execution_id),
                    },
                )
            )
        return approval

    async def expire_stale(self, organization_id: UUID) -> list[AutomationApproval]:
        """Mark every pending, past-expiry approval for *organization_id*
        as expired ("Approval Expiration").
        """
        now = datetime.now(UTC)
        expired: list[AutomationApproval] = []
        for approval in await self.list_pending_for_org(organization_id):
            if approval.expires_at is not None and approval.expires_at <= now:
                approval.status = ApprovalStatus.EXPIRED
                expired.append(await self._approvals.update(approval))
        return expired


__all__ = ["AutomationApprovalService"]
