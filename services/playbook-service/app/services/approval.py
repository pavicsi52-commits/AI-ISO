"""Playbook approval workflow. Per docs/041 "APPROVALS" "Support":
Technical Approval, Security Approval, Operational Approval, Publishing
Approval, Approval History, Comments, Revisions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.playbook_events import PlaybookApprovedEvent, PlaybookRejectedEvent
from app.models.enums import ApprovalStatus, ApprovalType
from app.models.playbook_approval import PlaybookApproval
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class PlaybookApprovalService:
    """Requests and decides playbook approval-workflow steps."""

    def __init__(
        self,
        approvals: PlaybookApprovalRepository,
        playbooks: PlaybookRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._approvals = approvals
        self._playbooks = playbooks
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, approval_id: UUID) -> PlaybookApproval:
        """Return the approval step identified by *approval_id*.

        Raises:
            NotFoundError: If no such approval step exists.
        """
        return await self._approvals.require_by_id(approval_id)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookApproval]:
        """Every approval step recorded for *playbook_id* ("Approval History")."""
        return await self._approvals.list_for_playbook(playbook_id)

    async def list_pending_for_org(self, organization_id: UUID) -> list[PlaybookApproval]:
        """Every still-pending approval for *organization_id*."""
        return await self._approvals.list_pending_for_org(organization_id)

    async def request(
        self,
        playbook_id: UUID,
        *,
        version_id: UUID | None,
        approval_type: ApprovalType,
        level: int,
        requested_by: UUID | None,
    ) -> PlaybookApproval:
        """Request a new approval-workflow step.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._approvals.create(
            PlaybookApproval(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                version_id=version_id,
                approval_type=approval_type,
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
    ) -> PlaybookApproval:
        """Approve or reject an approval step ("Revisions"), publishing
        ``PlaybookApproved``/``PlaybookRejected``.
        """
        approval = await self.get_by_id(approval_id)
        approval.status = status
        approval.approver_id = approver_id
        approval.comments = comments
        approval.decided_at = datetime.now(UTC)
        approval = await self._approvals.update(approval)

        payload = {"approval_id": str(approval_id), "playbook_id": str(approval.playbook_id)}
        if status is ApprovalStatus.APPROVED:
            await self._publish(
                PlaybookApprovedEvent(source_service="playbook-service", payload=payload)
            )
        elif status is ApprovalStatus.REJECTED:
            await self._publish(
                PlaybookRejectedEvent(source_service="playbook-service", payload=payload)
            )
        return approval


__all__ = ["PlaybookApprovalService"]
