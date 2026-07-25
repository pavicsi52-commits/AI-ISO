"""Multi-level approval workflow for configuration profiles/versions/rollbacks.

Per docs/039 "APPROVALS" "Support": Approval Workflow, Multi-Level
Approval, Approval History, Comments, Rejection, Resubmission,
Notifications.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.configuration_events import ConfigurationApprovedEvent, ConfigurationRejectedEvent
from app.models.configuration_approval import ConfigurationApproval
from app.models.enums import ApprovalStatus
from app.repositories.configuration_approval import ConfigurationApprovalRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationApprovalService:
    """Requests and decides configuration approval-workflow steps."""

    def __init__(
        self,
        approvals: ConfigurationApprovalRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._approvals = approvals
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, approval_id: UUID) -> ConfigurationApproval:
        """Return the approval step identified by *approval_id*.

        Raises:
            NotFoundError: If no such approval step exists.
        """
        return await self._approvals.require_by_id(approval_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationApproval]:
        """Every approval step recorded for *profile_id* ("Approval History")."""
        return await self._approvals.list_for_profile(profile_id)

    async def list_pending_for_org(self, organization_id: UUID) -> list[ConfigurationApproval]:
        """Every still-pending approval for *organization_id*."""
        return await self._approvals.list_pending_for_org(organization_id)

    async def request(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID | None,
        version_id: UUID | None,
        rollback_id: UUID | None,
        level: int,
        requested_by: UUID | None,
    ) -> ConfigurationApproval:
        """Request a new approval-workflow step ("Approval Workflow"/"Multi-Level Approval")."""
        return await self._approvals.create(
            ConfigurationApproval(
                organization_id=organization_id,
                profile_id=profile_id,
                version_id=version_id,
                rollback_id=rollback_id,
                status=ApprovalStatus.PENDING,
                level=level,
                requested_by=requested_by,
            )
        )

    async def decide(
        self,
        approval_id: UUID,
        *,
        status: ApprovalStatus,
        approver_id: UUID | None,
        comments: str | None,
    ) -> ConfigurationApproval:
        """Approve or reject an approval step ("Rejection"), publishing
        ``ConfigurationApproved``/``ConfigurationRejected``.
        """
        approval = await self.get_by_id(approval_id)
        approval.status = status
        approval.approver_id = approver_id
        approval.comments = comments
        approval.decided_at = datetime.now(UTC)
        approval = await self._approvals.update(approval)

        if status is ApprovalStatus.APPROVED:
            await self._publish(
                ConfigurationApprovedEvent(
                    source_service="configuration-management-service",
                    payload={"approval_id": str(approval_id)},
                )
            )
        elif status is ApprovalStatus.REJECTED:
            await self._publish(
                ConfigurationRejectedEvent(
                    source_service="configuration-management-service",
                    payload={"approval_id": str(approval_id)},
                )
            )
        return approval

    async def resubmit(self, approval_id: UUID) -> ConfigurationApproval:
        """Reopen a rejected approval step for another decision ("Resubmission")."""
        approval = await self.get_by_id(approval_id)
        approval.status = ApprovalStatus.RESUBMITTED
        approval.decided_at = None
        return await self._approvals.update(approval)


__all__ = ["ConfigurationApprovalService"]
