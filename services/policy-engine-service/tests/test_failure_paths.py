"""The branches that only run once something has already gone wrong.

Every test here covers a place where this service deliberately degrades
rather than fails. That choice only counts as behaviour if it is
exercised: the characteristic failure of an untested fallback is that it
turns out to raise, at precisely the moment nothing else is working.

This service answers every protected operation on the platform, so the
blast radius of "the fallback also broke" is not one request -- it is
every authorization decision anywhere, which is the whole estate.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.attributes.resolver import EvaluationContext
from app.models.enums import (
    ActionType,
    PolicyEffect,
    QuotaScope,
    ResourceType,
    SubjectType,
)
from app.notifications.policy_notifications import PolicyNotificationService
from app.repositories.policy import PolicyAttributeRepository, PolicyRepository
from app.repositories.runtime import (
    PolicyDecisionRepository,
    PolicyExceptionRepository,
    PolicyQuotaRepository,
)
from app.services.decision import DecisionRequest, DecisionService
from app.services.policy import PolicyService
from app.services.quota import QuotaService
from app.services.simulation import SimulationService
from app.simulation.engine import SimulationRequest

from .conftest import PublishedPolicyFn, RecordingPublisher


def _request(label: str = "probe") -> SimulationRequest:
    return SimulationRequest(
        label=label,
        subject_type=SubjectType.USER,
        resource_type=ResourceType.DASHBOARD,
        action=ActionType.READ,
        context=EvaluationContext(subject={"department": "platform"}),
    )


class TestDegradedPaths:
    async def test_a_draft_that_will_not_compile_is_left_out_not_fatal(
        self,
        simulation_service: SimulationService,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        """A rule-less draft is skipped; the preview still answers.

        "This draft cannot be published yet" is a real answer to the
        question the caller asked, and it is far more useful delivered as
        a policy missing from the preview than as a failed simulation
        that says nothing about the drafts that *were* fine.
        """
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        empty = await policy_service.create_policy(
            organization_id,
            slug="no-rules-yet",
            name="No rules yet",
            effect=PolicyEffect.DENY,
        )

        result = await simulation_service.preview(
            organization_id,
            requests=[_request()],
            draft_policy_ids=[empty.id],
        )

        assert result["changed_count"] == 0, "the uncompilable deny never entered the catalogue"
        assert result["safe"] is True
        assert result["breaking_changes"] == []

    async def test_quota_exhaustion_is_counted_published_and_announced(
        self,
        quota_service: QuotaService,
        db_session: AsyncSession,
        publisher: RecordingPublisher,
        organization_id: uuid.UUID,
    ) -> None:
        """Exhaustion is recorded even though notifying cannot work.

        The notification service here has no channel registered, so the
        send genuinely fails -- and the counter and the domain event must
        survive that, because they are the durable record of a budget
        having blocked real work.
        """
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="api-requests",
            limit_value=1,
        )
        quota.consumed = 1.0
        await db_session.flush()

        states = await quota_service.state_for(
            organization_id, scopes=[(QuotaScope.ORGANIZATION, str(organization_id))]
        )
        assert states[0].exceeded

        await quota_service.report_exhaustion(
            organization_id, states[0], quota_id=quota.id, notify_user_id="user-1"
        )

        assert "QuotaExceeded" in publisher.names
        await db_session.refresh(quota)
        assert quota.exceeded_count == 1
        assert quota.exceeded_at is not None

    async def test_a_decision_that_cannot_be_logged_still_stands(
        self,
        db_session: AsyncSession,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        """The answer survives an unwritable decision log.

        Forced with a subject id far past the column width, so a genuine
        database error is what gets swallowed rather than a simulated
        one. Refusing to answer here would convert a full decision-log
        table into a platform-wide authorization outage; the cost of the
        alternative is a gap in the evidence, and that is the trade this
        service makes on purpose.

        Run against its own service instance because the failed write
        poisons the transaction -- which is exactly what would happen in
        production, and why nothing may be asked of the session after.
        """
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        service = DecisionService(
            PolicyRepository(db_session),
            PolicyDecisionRepository(db_session),
            PolicyExceptionRepository(db_session),
            PolicyQuotaRepository(db_session),
            PolicyAttributeRepository(db_session),
        )

        decision, stored = await service.decide(
            DecisionRequest(
                organization_id=organization_id,
                subject_type=SubjectType.USER,
                subject_id="x" * 5_000,
                resource_type=ResourceType.DASHBOARD,
                action=ActionType.READ,
                context=EvaluationContext(subject={"department": "platform"}),
            )
        )

        assert decision.permitted is True, "the decision was made before it was logged"
        assert stored is None, "and the failed write was swallowed, not raised"

    async def test_no_notification_failure_can_block_its_caller(
        self, notifications: PolicyNotificationService
    ) -> None:
        """Every send survives having nowhere to send to.

        The fixture registers no channel, so all six of these genuinely
        fail. Each one sits on a path that decides or records something:
        a notification that could raise would let an unreachable SMTP
        host take down authorization for the entire platform.
        """
        send = notifications

        await send.send_violation(
            "user-1", title="Export blocked", severity="high", detail="Outside window"
        )
        await send.send_approval_required(
            "user-1", resource="cluster-a", action="deploy", expires_at="2026-08-01T00:00:00Z"
        )
        await send.send_quota_exceeded(
            "user-1", resource="api-requests", consumed=100.0, limit=100.0
        )
        await send.send_quota_warning("user-1", resource="api-requests", percent=80)
        await send.send_policy_published(
            "user-1", slug="prod-deploy", version="1.0.1", effect="deny"
        )
        await send.send_simulation_completed(
            "user-1", label="what-if", summary="3 decisions would change"
        )
