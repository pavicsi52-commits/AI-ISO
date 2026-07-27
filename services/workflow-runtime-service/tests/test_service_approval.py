"""Tests for :class:`app.services.approval.WorkflowApprovalService`."""

from __future__ import annotations

import pytest
from shared_core.workflow import ApprovalRejectedError, ApprovalTimeoutError, NodeType
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalDecisionStatus
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.services.approval import WorkflowApprovalService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowApprovalService:
    return WorkflowApprovalService(WorkflowApprovalRepository(db_session))


async def _linear_instance(db_session: AsyncSession) -> WorkflowInstance:
    definition = await make_definition(db_session)
    version = await build_version_service(db_session).create_version(
        definition,
        nodes=[
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        edges=[{"from_node_id": "start", "to_node_id": "end"}],
        current_version_number=None,
    )
    return await make_instance(db_session, definition, version)


class TestWorkflowApprovalService:
    async def test_request_creates_pending_approval(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        assert approval.decision == ApprovalDecisionStatus.PENDING
        assert approval.approvers == ["alice"]

    async def test_decide_approve_with_required_approvals_met_resolves_approved(
        self, db_session: AsyncSession
    ) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
            required_approvals=1,
        )
        decided = await service.decide(approval.id, approver="alice", approve=True, comments="LGTM")
        assert decided.decision == ApprovalDecisionStatus.APPROVED
        assert decided.decided_at is not None
        assert decided.comments == "LGTM"

    async def test_decide_approve_below_required_approvals_stays_pending(
        self, db_session: AsyncSession
    ) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice", "bob"],
            required_approvals=2,
        )
        decided = await service.decide(approval.id, approver="alice", approve=True, comments=None)
        assert decided.decision == ApprovalDecisionStatus.PENDING

        decided = await service.decide(approval.id, approver="bob", approve=True, comments=None)
        assert decided.decision == ApprovalDecisionStatus.APPROVED

    async def test_decide_reject_resolves_immediately(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice", "bob"],
            required_approvals=2,
        )
        decided = await service.decide(approval.id, approver="alice", approve=False, comments="No.")
        assert decided.decision == ApprovalDecisionStatus.REJECTED
        assert decided.decided_at is not None

    async def test_escalate(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        escalated = await service.escalate(approval.id, escalate_to="manager")
        assert escalated.escalated_to == "manager"
        assert escalated.decision == ApprovalDecisionStatus.ESCALATED

    async def test_list_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        approvals = await service.list_for_instance(instance.id)
        assert len(approvals) == 1

    async def test_list_pending_for_org(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        pending = await service.list_pending_for_org(instance.organization_id)
        assert len(pending) == 1

    async def test_wait_for_decision_returns_immediately_when_already_approved(
        self, db_session: AsyncSession
    ) -> None:
        """Decide first, then wait -- the first poll iteration already
        finds it resolved, so this never actually sleeps. Safe,
        sequential coverage of the success path -- see
        ``tests/test_service_execution.py``'s own module docstring for
        why a genuinely concurrent decide-while-waiting test is
        deliberately avoided.
        """
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        await service.decide(approval.id, approver="alice", approve=True, comments=None)

        resolved = await service.wait_for_decision(approval.id, poll_interval_seconds=0.01)
        assert resolved.decision == ApprovalDecisionStatus.APPROVED

    async def test_wait_for_decision_raises_when_already_rejected(
        self, db_session: AsyncSession
    ) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )
        await service.decide(approval.id, approver="alice", approve=False, comments=None)

        with pytest.raises(ApprovalRejectedError):
            await service.wait_for_decision(approval.id, poll_interval_seconds=0.01)

    async def test_wait_for_decision_times_out(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        approval = await service.request(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
            timeout_seconds=0.01,
        )
        with pytest.raises(ApprovalTimeoutError):
            await service.wait_for_decision(approval.id, poll_interval_seconds=0.005)

        expired = await service.get_by_id(approval.id)
        assert expired.decision == ApprovalDecisionStatus.EXPIRED


__all__: list[str] = []
