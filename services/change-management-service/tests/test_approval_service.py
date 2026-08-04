"""ApprovalService: requesting and deciding a change's approval chain.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from tests.conftest import ago, utcnow

from app.models.approval import ChangeApproval
from app.models.enums import (
    ApprovalPolicy,
    ApprovalStatus,
    ChangeStatus,
    RiskImpact,
    RiskLikelihood,
)
from app.risk.engine import RiskDimensions
from app.services.approval import ApprovalService
from app.services.change import ChangeService

pytestmark = pytest.mark.asyncio

_CRITICAL_DIMENSIONS = RiskDimensions(
    technical=RiskImpact.SEVERE,
    business=RiskImpact.SEVERE,
    operational=RiskImpact.SEVERE,
    security=RiskImpact.SEVERE,
    compliance=RiskImpact.SEVERE,
    dependency=RiskImpact.SEVERE,
)

_HIGH_DIMENSIONS = RiskDimensions(
    technical=RiskImpact.MODERATE,
    business=RiskImpact.MODERATE,
    operational=RiskImpact.MODERATE,
    security=RiskImpact.MODERATE,
    compliance=RiskImpact.MODERATE,
    dependency=RiskImpact.MODERATE,
)


class TestRequestApprovals:
    async def test_wrong_status_raises_conflict_error(
        self, approval_service: ApprovalService, organization_id, make_change
    ) -> None:
        created = await make_change()
        with pytest.raises(ConflictError):
            await approval_service.request_approvals(
                organization_id,
                created.id,
                policy=ApprovalPolicy.SINGLE,
                approvers=[("approver-1", None)],
            )

    async def test_single_policy_requires_exactly_one_approver_regardless_of_risk(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk
        created = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        assert len(created) == 1
        assert created[0].level == 1

    async def test_multi_level_requires_two_approvers_even_at_medium_risk(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk
        with pytest.raises(ConflictError):
            await approval_service.request_approvals(
                organization_id,
                change.id,
                policy=ApprovalPolicy.MULTI_LEVEL,
                approvers=[("approver-1", None)],
            )
        created = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.MULTI_LEVEL,
            approvers=[("approver-1", "manager"), ("approver-2", "director")],
        )
        assert [one.level for one in created] == [1, 2]
        assert created[1].approver_role == "director"

    async def test_role_based_requires_two_approvers(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk
        with pytest.raises(ConflictError):
            await approval_service.request_approvals(
                organization_id,
                change.id,
                policy=ApprovalPolicy.ROLE_BASED,
                approvers=[("approver-1", "manager")],
            )

    async def test_risk_based_requires_one_approver_for_medium_risk(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk
        created = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.RISK_BASED,
            approvers=[("approver-1", None)],
        )
        assert len(created) == 1

    async def test_risk_based_requires_two_approvers_for_high_risk(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        risk_service,
        organization_id,
        make_change,
    ) -> None:
        created = await make_change()
        await change_service.submit(organization_id, created.id)
        await risk_service.assess(
            organization_id,
            created.id,
            likelihood=RiskLikelihood.POSSIBLE,
            dimensions=_HIGH_DIMENSIONS,
        )
        with pytest.raises(ConflictError):
            await approval_service.request_approvals(
                organization_id,
                created.id,
                policy=ApprovalPolicy.RISK_BASED,
                approvers=[("approver-1", None)],
            )
        created_steps = await approval_service.request_approvals(
            organization_id,
            created.id,
            policy=ApprovalPolicy.RISK_BASED,
            approvers=[("approver-1", None), ("approver-2", None)],
        )
        assert len(created_steps) == 2

    async def test_risk_based_treats_an_unassessed_risk_level_as_high(
        self,
        approval_service: ApprovalService,
        changes_repo,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        stored = await changes_repo.require_in_org(organization_id, change.id)
        stored.risk_level = None
        await changes_repo.update(stored)
        with pytest.raises(ConflictError):
            await approval_service.request_approvals(
                organization_id,
                change.id,
                policy=ApprovalPolicy.RISK_BASED,
                approvers=[("approver-1", None)],
            )
        created = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.RISK_BASED,
            approvers=[("approver-1", None), ("approver-2", None)],
        )
        assert len(created) == 2


class TestDecide:
    async def test_single_level_approval_resolves_without_leaving_pending_approval(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
        publisher,
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk, CAB not required
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        decided = await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        assert decided.status == ApprovalStatus.APPROVED
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.PENDING_APPROVAL
        assert updated.approved_at is not None
        assert updated.approval_duration_seconds is not None
        assert "ChangeApproved" in publisher.names

    async def test_a_conditional_decision_also_resolves_the_chain_favourably(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.CONDITIONAL
        )
        updated = await change_service.get(organization_id, change.id)
        assert updated.approved_at is not None

    async def test_a_rejection_sinks_the_whole_chain_regardless_of_other_levels(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
        publisher,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.MULTI_LEVEL,
            approvers=[("approver-1", None), ("approver-2", None)],
        )
        level_one = next(one for one in approvals if one.level == 1)
        await approval_service.decide(
            organization_id, level_one.id, decision=ApprovalStatus.REJECTED
        )
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.REJECTED
        assert "ChangeApproved" not in publisher.names

    async def test_a_still_pending_level_does_not_advance_the_change_or_publish(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
        publisher,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.MULTI_LEVEL,
            approvers=[("approver-1", None), ("approver-2", None)],
        )
        level_one = next(one for one in approvals if one.level == 1)
        await approval_service.decide(
            organization_id, level_one.id, decision=ApprovalStatus.APPROVED
        )
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.PENDING_APPROVAL
        assert updated.approved_at is None
        assert "ChangeApproved" not in publisher.names

    async def test_a_favourable_resolution_moves_the_change_to_cab_review_when_required(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
        publisher,
    ) -> None:
        change = await make_assessed_change(
            likelihood=RiskLikelihood.ALMOST_CERTAIN, dimensions=_CRITICAL_DIMENSIONS
        )
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.CAB_REVIEW
        assert updated.approved_at is not None
        assert "ChangeApproved" in publisher.names

    async def test_deciding_an_already_resolved_step_raises_conflict_error(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        with pytest.raises(ConflictError):
            await approval_service.decide(
                organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
            )


class TestDelegate:
    async def test_closes_the_original_step_and_opens_a_new_pending_step_at_the_same_level(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        original = approvals[0]
        delegated = await approval_service.delegate(
            organization_id, original.id, delegated_to="approver-2"
        )
        steps = await approval_service.list_for_change(organization_id, change.id)
        closed = next(one for one in steps if one.id == original.id)
        assert closed.status == ApprovalStatus.DELEGATED
        assert closed.delegated_to == "approver-2"
        assert delegated.status == ApprovalStatus.PENDING
        assert delegated.level == original.level
        assert delegated.approver_id == "approver-2"
        assert delegated.delegated_from == "approver-1"

    async def test_raises_conflict_error_if_the_original_step_has_already_resolved(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        with pytest.raises(ConflictError):
            await approval_service.delegate(
                organization_id, approvals[0].id, delegated_to="approver-2"
            )

    async def test_the_delegates_decision_still_resolves_the_chain(
        self,
        approval_service: ApprovalService,
        change_service: ChangeService,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        delegated = await approval_service.delegate(
            organization_id, approvals[0].id, delegated_to="approver-2"
        )
        await approval_service.decide(
            organization_id, delegated.id, decision=ApprovalStatus.APPROVED
        )
        updated = await change_service.get(organization_id, change.id)
        assert updated.approved_at is not None


class TestSweepExpired:
    async def test_marks_overdue_pending_steps_expired_and_returns_the_count(
        self,
        approval_service: ApprovalService,
        approvals_repo,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        stored = await approvals_repo.require_in_org(organization_id, approvals[0].id)
        stored.expires_at = ago(hours=1)
        await approvals_repo.update(stored)

        expired = await approval_service.sweep_expired(organization_id, now=utcnow())
        assert expired == 1
        steps = await approval_service.list_for_change(organization_id, change.id)
        assert steps[0].status == ApprovalStatus.EXPIRED

    async def test_does_not_touch_steps_that_are_still_within_their_expiry(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        expired = await approval_service.sweep_expired(organization_id, now=utcnow())
        assert expired == 0
        steps = await approval_service.list_for_change(organization_id, change.id)
        assert steps[0].status == ApprovalStatus.PENDING

    async def test_does_not_touch_steps_that_have_already_resolved(
        self,
        approval_service: ApprovalService,
        approvals_repo,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        approvals = await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.SINGLE,
            approvers=[("approver-1", None)],
        )
        await approval_service.decide(
            organization_id, approvals[0].id, decision=ApprovalStatus.APPROVED
        )
        stored = await approvals_repo.require_in_org(organization_id, approvals[0].id)
        stored.expires_at = ago(hours=1)
        await approvals_repo.update(stored)

        expired = await approval_service.sweep_expired(organization_id, now=utcnow())
        assert expired == 0

    async def test_only_sweeps_the_given_organization(
        self,
        approval_service: ApprovalService,
        approvals_repo,
        organization_id,
        make_assessed_change,
    ) -> None:
        change = await make_assessed_change()
        other_org_id = uuid4()
        own_row = await approvals_repo.create(
            ChangeApproval(
                organization_id=organization_id,
                change_id=change.id,
                policy=ApprovalPolicy.SINGLE,
                level=1,
                approver_id="approver-1",
                status=ApprovalStatus.PENDING,
                expires_at=ago(hours=1),
            )
        )
        other_org_row = await approvals_repo.create(
            ChangeApproval(
                organization_id=other_org_id,
                change_id=change.id,
                policy=ApprovalPolicy.SINGLE,
                level=1,
                approver_id="approver-1",
                status=ApprovalStatus.PENDING,
                expires_at=ago(hours=1),
            )
        )

        expired = await approval_service.sweep_expired(organization_id, now=utcnow())
        assert expired == 1
        refreshed_own = await approvals_repo.require_in_org(organization_id, own_row.id)
        assert refreshed_own.status == ApprovalStatus.EXPIRED
        refreshed_other = await approvals_repo.require_in_org(other_org_id, other_org_row.id)
        assert refreshed_other.status == ApprovalStatus.PENDING


class TestListForChange:
    async def test_lists_every_step_ordered_by_level(
        self, approval_service: ApprovalService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        await approval_service.request_approvals(
            organization_id,
            change.id,
            policy=ApprovalPolicy.MULTI_LEVEL,
            approvers=[("approver-1", None), ("approver-2", None)],
        )
        steps = await approval_service.list_for_change(organization_id, change.id)
        assert [one.level for one in steps] == [1, 2]
