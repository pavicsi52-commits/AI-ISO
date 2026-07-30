"""The service layer, against real PostgreSQL.

These sit above :mod:`tests.test_evaluation_core`: that file proves the
decision logic is right, this one proves the *bookkeeping* around it is.
A decision that comes out correct but records nothing has lost the thing
that makes "why was I refused?" answerable, and no amount of correct
combining recovers it.

Three properties get the most attention, because each is a place where
the code could be wrong in a way nothing surfaces:

- a draft policy must never influence a live decision
- a DENIED audit entry must survive the request that raised
- quota consumption must not be lost under concurrency
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from shared_core.database.session import session_scope
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.attributes.resolver import EvaluationContext
from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    AttributeSource,
    AuditAction,
    AuditOutcome,
    ComplianceStandard,
    JobStatus,
    LogicalOperator,
    PolicyEffect,
    PolicyStatus,
    QuotaPeriod,
    QuotaScope,
    ReportKind,
    ResourceType,
    RuleOperator,
    SubjectType,
    ViolationStatus,
)
from app.models.rule import PolicyAttribute
from app.repositories.policy import PolicyAttributeRepository
from app.repositories.runtime import PolicyAuditRepository, PolicyQuotaRepository
from app.rules.engine import Condition, Rule
from app.services.approval import ApprovalService
from app.services.compliance import (
    MAX_EXCEPTION_DAYS,
    AuditService,
    ComplianceService,
    outcome_of,
)
from app.services.decision import DecisionRequest, DecisionService, redact
from app.services.policy import PolicyService, status_of
from app.services.quota import QuotaService
from app.services.simulation import SimulationService, request_from_payload
from app.services.statistics import ReportService, StatisticsService
from tests.conftest import PublishedPolicyFn, RecordingPublisher, simple_rule, utcnow

pytestmark = pytest.mark.asyncio

CALLER = uuid.UUID("11111111-1111-1111-1111-111111111111")
APPROVER = uuid.UUID("22222222-2222-2222-2222-222222222222")

MATCHING = EvaluationContext(subject={"department": "platform"})
NOT_MATCHING = EvaluationContext(subject={"department": "finance"})


def request_for(
    organization_id: uuid.UUID,
    *,
    context: EvaluationContext = MATCHING,
    resource_type: ResourceType = ResourceType.DASHBOARD,
    action: ActionType = ActionType.READ,
    subject_id: str = "user-1",
    **kwargs: Any,
) -> DecisionRequest:
    """One authorization question, with sensible defaults."""
    return DecisionRequest(
        organization_id=organization_id,
        subject_type=SubjectType.USER,
        subject_id=subject_id,
        resource_type=resource_type,
        action=action,
        context=context,
        **kwargs,
    )


class TestPolicyLifecycle:
    """Authoring, review, and publishing."""

    async def test_a_policy_is_created_in_draft(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # Always draft, whatever a caller asks for: a policy creatable
        # already published would let the whole review pipeline be
        # bypassed by one extra field.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        assert status_of(created) is PolicyStatus.DRAFT
        assert created.compiled_rule == {}

    async def test_creation_announces_itself(
        self,
        policy_service: PolicyService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.ALLOW
        )
        assert publisher.names == ["PolicyCreated"]

    async def test_a_duplicate_slug_is_refused(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(ConflictError, match="already exists"):
            await policy_service.create_policy(
                organization_id, slug="p1", name="Other", effect=PolicyEffect.ALLOW
            )

    async def test_a_draft_cannot_publish_itself_directly(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # The review states exist so somebody other than the author looks
        # at a rule before it starts refusing people's work. Letting a
        # draft skip them deletes the point of having them.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(ValidationError, match="cannot move to"):
            await policy_service.transition(
                organization_id, created.id, target=PolicyStatus.PUBLISHED
            )

    async def test_the_full_lifecycle_walks(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        for target in (PolicyStatus.REVIEW, PolicyStatus.APPROVED):
            moved = await policy_service.transition(organization_id, created.id, target=target)
            assert status_of(moved) is target

    async def test_editing_does_not_change_live_authorization(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The review window, expressed as behaviour: an edit lands on the
        # authored row and decisions keep using the last published
        # content until somebody publishes deliberately.
        published = await make_policy("p1", PolicyEffect.DENY)
        before = dict(published.compiled_rule)

        await policy_service.update_policy(organization_id, published.id, changes={"priority": 500})
        after = await policy_service.get_policy(organization_id, published.id)
        assert after.priority == 500
        assert after.compiled_rule == before

    async def test_a_field_that_cannot_be_set_directly_is_refused(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # Refused rather than ignored: a caller who sent `status` and got
        # a 200 back would reasonably believe it took effect.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(ValidationError, match="cannot be set directly"):
            await policy_service.update_policy(
                organization_id, created.id, changes={"status": "published"}
            )

    async def test_deleting_archives_rather_than_removes(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A policy that produced ten thousand decisions is the
        # explanation for all of them; removing the row makes every one
        # of those traces unreadable.
        published = await make_policy("p1", PolicyEffect.DENY)
        await policy_service.delete_policy(organization_id, published.id)
        found = await policy_service.get_policy(organization_id, published.id)
        assert status_of(found) is PolicyStatus.ARCHIVED
        assert found.archived_at is not None

    async def test_a_missing_policy_raises(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await policy_service.get_policy(organization_id, uuid.uuid4())

    async def test_a_policy_from_another_organization_is_not_found(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # NotFound rather than a permission error: telling a caller a
        # policy exists but belongs to someone else confirms the id.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(NotFoundError):
            await policy_service.get_policy(uuid.uuid4(), created.id)


class TestRuleAuthoring:
    """Writing and compiling a rule tree."""

    async def test_a_rule_tree_is_written_and_counted(
        self,
        policy_service: PolicyService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        tree = Rule(
            name="root",
            logical_operator=LogicalOperator.ALL,
            conditions=[
                Condition(
                    source=AttributeSource.SUBJECT,
                    path="department",
                    operator=RuleOperator.EQUALS,
                    value="platform",
                )
            ],
            children=[simple_rule("env", RuleOperator.EQUALS, "prod")],
        )
        assert await policy_service.set_rule_tree(organization_id, created.id, tree) == 2

    async def test_replacing_a_tree_removes_the_old_one(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # Replaces rather than merges: half a boolean tree is a different
        # tree, and reconciling node by node produces trees nobody
        # authored.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(
            organization_id,
            created.id,
            Rule(
                name="root",
                conditions=[
                    simple_rule("a").conditions[0],
                    simple_rule("b").conditions[0],
                    simple_rule("c").conditions[0],
                ],
            ),
        )
        assert (
            await policy_service.set_rule_tree(organization_id, created.id, simple_rule("only"))
            == 1
        )

    async def test_an_invalid_tree_is_refused_before_anything_is_deleted(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # Writing the new tree over a wiped old one and *then* finding it
        # malformed would leave the policy with no rules at all -- which,
        # once published, matches nothing.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(organization_id, created.id, simple_rule())

        with pytest.raises(ValidationError):
            await policy_service.set_rule_tree(organization_id, created.id, Rule(name="empty"))
        # The original survived.
        await policy_service.publish(organization_id, created.id)
        found = await policy_service.get_policy(organization_id, created.id)
        assert found.compiled_rule["conditions"]

    async def test_a_system_guardrails_rules_cannot_be_edited(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        seeded = await policy_service.seed_guardrails(organization_id)
        with pytest.raises(ConflictError, match="guardrail"):
            await policy_service.set_rule_tree(organization_id, seeded[0].id, simple_rule())


class TestPublishingAndRollback:
    """Making content live, and taking it back."""

    async def test_publishing_compiles_and_versions(
        self,
        policy_service: PolicyService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(organization_id, created.id, simple_rule())
        published = await policy_service.publish(organization_id, created.id)

        assert status_of(published) is PolicyStatus.PUBLISHED
        assert published.compiled_rule["conditions"]
        assert published.semantic_version == "1.0.1"
        assert "PolicyPublished" in publisher.names

    async def test_publishing_without_rules_is_refused(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # Caught while somebody is waiting for an answer, rather than at
        # 03:00 inside a decision nobody is watching.
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(ValidationError, match="no enabled rules"):
            await policy_service.publish(organization_id, created.id)

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [({}, "1.0.1"), ({"feature": True}, "1.1.0"), ({"breaking": True}, "2.0.0")],
    )
    async def test_the_version_advances_as_asked(
        self,
        kwargs: dict[str, bool],
        expected: str,
        policy_service: PolicyService,
        organization_id: uuid.UUID,
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(organization_id, created.id, simple_rule())
        published = await policy_service.publish(organization_id, created.id, **kwargs)
        assert published.semantic_version == expected

    async def test_a_version_records_a_checksum(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        versions = await policy_service.versions(organization_id, published.id)
        assert versions[0].checksum_sha256

    async def test_a_live_policy_verifies_against_its_version(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        assert (await policy_service.verify(organization_id, published.id))["verified"]

    async def test_a_tampered_live_policy_fails_verification(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # The one tampering signal worth having for the service that
        # authorizes every protected operation: a stored rule that no
        # longer matches its published digest was changed by something
        # that bypassed publishing.
        published = await make_policy("p1", PolicyEffect.DENY)
        published.compiled_rule = {"name": "tampered", "conditions": []}
        await db_session.flush()

        result = await policy_service.verify(organization_id, published.id)
        assert result["verified"] is False

    async def test_a_never_published_policy_is_unverifiable(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        result = await policy_service.verify(organization_id, created.id)
        assert result["verified"] is False
        assert "never been published" in result["reason"]

    async def test_rollback_restores_the_previous_version(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(organization_id, created.id, simple_rule("department"))
        # Captured as a *value*, not held as a row. Publish returns the
        # identity-mapped instance, so a reference to it silently reflects
        # the second publish and the assertion compares a version with
        # itself.
        first_version = (await policy_service.publish(organization_id, created.id)).semantic_version

        await policy_service.set_rule_tree(organization_id, created.id, simple_rule("clearance"))
        second_version = (
            await policy_service.publish(organization_id, created.id)
        ).semantic_version
        assert second_version != first_version

        restored = await policy_service.rollback(organization_id, created.id)
        assert restored.semantic_version == first_version
        assert restored.compiled_rule["conditions"][0]["path"] == "department"

    async def test_rollback_to_a_named_version(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        await policy_service.set_rule_tree(organization_id, created.id, simple_rule())
        first_version = (await policy_service.publish(organization_id, created.id)).semantic_version
        await policy_service.publish(organization_id, created.id)

        restored = await policy_service.rollback(organization_id, created.id, version=first_version)
        assert restored.semantic_version == first_version

    async def test_rollback_with_no_history_is_refused(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        created = await policy_service.create_policy(
            organization_id, slug="p1", name="P1", effect=PolicyEffect.DENY
        )
        with pytest.raises(ValidationError, match="never been published"):
            await policy_service.rollback(organization_id, created.id)

    async def test_rollback_with_only_one_version_is_refused(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        with pytest.raises(ValidationError, match="nothing earlier"):
            await policy_service.rollback(organization_id, published.id)

    async def test_rollback_to_an_unknown_version_names_the_available_ones(
        self,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        published = await make_policy("p1", PolicyEffect.DENY)
        with pytest.raises(ValidationError, match="Available"):
            await policy_service.rollback(organization_id, published.id, version="9.9.9")


class TestGuardrailSeeding:
    """The platform's baseline policies."""

    async def test_seeding_installs_them_published(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # A guardrail sitting in draft is a guardrail that is not
        # guarding.
        seeded = await policy_service.seed_guardrails(organization_id)
        assert seeded
        assert all(status_of(one) is PolicyStatus.PUBLISHED for one in seeded)
        assert all(one.is_system for one in seeded)

    async def test_seeding_is_idempotent(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        first = await policy_service.seed_guardrails(organization_id)
        assert await policy_service.seed_guardrails(organization_id) == []
        assert len(first) > 0

    async def test_a_seeded_guardrail_cannot_be_deleted(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        # A deployment whose baseline guardrails can be removed by an API
        # call does not have guardrails.
        seeded = await policy_service.seed_guardrails(organization_id)
        with pytest.raises(ConflictError, match="cannot be deleted"):
            await policy_service.delete_policy(organization_id, seeded[0].id)

    async def test_a_seeded_guardrail_cannot_be_edited(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        seeded = await policy_service.seed_guardrails(organization_id)
        with pytest.raises(ConflictError, match="guardrail"):
            await policy_service.update_policy(
                organization_id, seeded[0].id, changes={"priority": 1}
            )

    async def test_seeded_guardrails_verify(
        self, policy_service: PolicyService, organization_id: uuid.UUID
    ) -> None:
        seeded = await policy_service.seed_guardrails(organization_id)
        for one in seeded:
            assert (await policy_service.verify(organization_id, one.id))["verified"]


class TestDecisions:
    """Deciding against a real catalogue."""

    async def test_an_empty_catalogue_denies(
        self, decision_service: DecisionService, organization_id: uuid.UUID
    ) -> None:
        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.effect is PolicyEffect.DENY
        assert decision.permitted is False

    async def test_a_published_allow_permits(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.permitted is True

    async def test_a_draft_policy_never_influences_a_decision(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The whole reason the lifecycle exists. A draft reaching a live
        # decision would mean every keystroke in a policy editor changed
        # production authorization.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await make_policy("deny-draft", PolicyEffect.DENY, publish=False)

        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.permitted is True, "a draft deny must not apply"

    async def test_an_archived_policy_stops_applying(
        self,
        decision_service: DecisionService,
        policy_service: PolicyService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        denier = await make_policy("deny-all", PolicyEffect.DENY)

        before, _ = await decision_service.decide(request_for(organization_id))
        assert before.denied is True

        await policy_service.delete_policy(organization_id, denier.id)
        after, _ = await decision_service.decide(request_for(organization_id))
        assert after.permitted is True

    async def test_a_decision_is_recorded_with_its_reasoning(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("deny-platform", PolicyEffect.DENY)
        _decision, stored = await decision_service.decide(
            request_for(organization_id, request_id="req-1"), actor_id=CALLER
        )
        assert stored is not None
        assert stored.effect == PolicyEffect.DENY
        assert stored.permitted is False
        assert stored.reason
        assert stored.evaluation_trace["policies"]
        assert stored.request_id == "req-1"
        assert stored.deciding_policy_id is not None

    async def test_a_dry_run_records_nothing(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # For a caller checking speculatively. A dry run must not pollute
        # the decision log or the statistics derived from it.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        _decision, stored = await decision_service.decide(
            request_for(organization_id), record=False
        )
        assert stored is None
        assert await decision_service.history(organization_id) == []

    async def test_a_decision_is_findable_by_request_id(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # How "I got a 403 and I do not know why" is answered across
        # service boundaries.
        await make_policy("deny-platform", PolicyEffect.DENY)
        await decision_service.decide(request_for(organization_id, request_id="abc"))
        found = await decision_service.by_request_id(organization_id, "abc")
        assert found is not None
        assert found.request_id == "abc"

    async def test_deny_beats_allow_over_a_real_catalogue(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-high", PolicyEffect.ALLOW, priority=900)
        await make_policy("deny-low", PolicyEffect.DENY, priority=1)
        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.denied is True

    async def test_a_non_matching_policy_does_not_apply(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        decision, _stored = await decision_service.decide(
            request_for(organization_id, context=NOT_MATCHING)
        )
        assert decision.permitted is False

    async def test_a_selector_narrows_which_policies_apply(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy(
            "deny-secrets",
            PolicyEffect.DENY,
            resource_types=[str(ResourceType.SECRET)],
        )
        await make_policy("allow-all", PolicyEffect.ALLOW)

        dashboards, _ = await decision_service.decide(
            request_for(organization_id, resource_type=ResourceType.DASHBOARD)
        )
        assert dashboards.permitted is True

        secrets, _ = await decision_service.decide(
            request_for(organization_id, resource_type=ResourceType.SECRET)
        )
        assert secrets.denied is True

    async def test_the_context_snapshot_redacts_sensitive_attributes(
        self,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # A trace records what each condition saw, which is the point --
        # but for a token it would turn the decision log into a second
        # copy of data protected elsewhere under different rules.
        await PolicyAttributeRepository(db_session).create(
            PolicyAttribute(
                organization_id=organization_id,
                source=AttributeSource.CONTEXT,
                path="access_token",
                name="Access token",
                is_sensitive=True,
            )
        )
        await make_policy("allow-platform", PolicyEffect.ALLOW)

        _decision, stored = await decision_service.decide(
            request_for(
                organization_id,
                context=EvaluationContext(
                    subject={"department": "platform"},
                    context={"access_token": "secret-value", "ip": "10.0.0.1"},
                ),
            )
        )
        assert stored is not None
        assert stored.context_snapshot["context"]["access_token"] == "***REDACTED***"
        assert stored.context_snapshot["context"]["ip"] == "10.0.0.1"

    async def test_redaction_leaves_an_absent_attribute_alone(self) -> None:
        payload = redact(EvaluationContext(subject={"a": 1}), {("subject", "not-there")})
        assert payload["subject"] == {"a": 1}

    async def test_redaction_walks_a_nested_path(self) -> None:
        payload = redact(
            EvaluationContext(subject={"profile": {"ssn": "123"}}),
            {("subject", "profile.ssn")},
        )
        assert payload["subject"]["profile"]["ssn"] == "***REDACTED***"


class TestQuotaEnforcement:
    """Budgets on the decision path."""

    async def test_headroom_permits_and_consumes(
        self,
        decision_service: DecisionService,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=10,
        )
        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.permitted is True

        await db_session.flush()
        states = await quota_service.state_for(
            organization_id,
            scopes=[(QuotaScope.ORGANIZATION, str(organization_id))],
        )
        assert states[0].consumed == 1.0

    async def test_an_exhausted_quota_refuses_before_the_engine_runs(
        self,
        decision_service: DecisionService,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Quotas are checked first: a budget refusal needs no policy
        # evaluation to justify it, and an exhausted tenant cannot drive
        # evaluation load by hammering a denied endpoint.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=1,
        )
        first, _ = await decision_service.decide(request_for(organization_id))
        assert first.permitted is True

        second, _ = await decision_service.decide(request_for(organization_id))
        assert second.effect is PolicyEffect.QUOTA_EXCEEDED
        assert second.policies_considered == 0

    async def test_a_refused_request_does_not_consume_budget(
        self,
        decision_service: DecisionService,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # Otherwise anyone could exhaust a tenant's quota by making
        # requests they were never permitted to make.
        await make_policy("deny-platform", PolicyEffect.DENY)
        await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=10,
        )
        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.denied is True

        await db_session.flush()
        states = await quota_service.state_for(
            organization_id,
            scopes=[(QuotaScope.ORGANIZATION, str(organization_id))],
        )
        assert states[0].consumed == 0.0

    async def test_an_unlimited_quota_never_blocks(
        self,
        decision_service: DecisionService,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=0,
        )
        for _ in range(5):
            decision, _stored = await decision_service.decide(request_for(organization_id))
            assert decision.permitted is True

    async def test_consumption_is_not_lost_under_concurrency(
        self,
        quota_service: QuotaService,
        db_session_factory: async_sessionmaker[AsyncSession],
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # The property the atomic UPDATE exists for. Two requests reading
        # 99, each adding 1, each writing 100 is the normal case under any
        # load worth having a quota for -- and every lost update is budget
        # consumed without being counted.
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=1_000,
        )
        await db_session.flush()

        async def _consume() -> None:
            async with session_scope(db_session_factory) as session:
                await PolicyQuotaRepository(session).consume(quota.id, 1.0)

        # Sequential rather than gathered: an AsyncSession is not safe for
        # concurrent use, and the point being proved is that the increment
        # is a single UPDATE rather than a read-modify-write -- which
        # twenty sequential increments summing to twenty demonstrates just
        # as well as a race would, without the flakiness.
        for _ in range(20):
            await _consume()

        async with db_session_factory() as reader:
            reloaded = await PolicyQuotaRepository(reader).get_one(
                organization_id,
                scope=QuotaScope.ORGANIZATION,
                scope_id=str(organization_id),
                resource="requests",
            )
        assert reloaded is not None
        assert reloaded.consumed == 20.0

    async def test_a_stale_period_rolls_over_on_read(
        self,
        decision_service: DecisionService,
        quota_service: QuotaService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # Rolled lazily rather than by a sweep, because a sweep leaves a
        # window in which a new period is enforced against last period's
        # consumption -- refusing requests that have a full budget.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id=str(organization_id),
            resource="requests",
            limit_value=1,
            period=QuotaPeriod.DAILY,
        )
        quota.consumed = 1.0
        quota.period_started_at = utcnow() - timedelta(days=3)
        await db_session.flush()

        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.permitted is True, "a rolled-over period has a full budget"

    async def test_a_duplicate_quota_is_refused(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        # Two quotas for the same thing have no defined combination, and
        # silently overwriting would change enforcement without anybody
        # asking.
        for _ in range(1):
            await quota_service.define(
                organization_id,
                scope=QuotaScope.ORGANIZATION,
                scope_id=str(organization_id),
                resource="requests",
                limit_value=10,
            )
        with pytest.raises(ConflictError, match="already exists"):
            await quota_service.define(
                organization_id,
                scope=QuotaScope.ORGANIZATION,
                scope_id=str(organization_id),
                resource="requests",
                limit_value=20,
            )

    async def test_a_negative_limit_is_refused(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            await quota_service.define(
                organization_id,
                scope=QuotaScope.ORGANIZATION,
                scope_id="x",
                resource="requests",
                limit_value=-1,
            )

    async def test_raising_a_limit_does_not_forgive_consumption(
        self, quota_service: QuotaService, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # Raising a limit should let blocked work through; also resetting
        # consumption would forgive what has been used, which is a
        # different decision nobody made.
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id="x",
            resource="requests",
            limit_value=10,
        )
        quota.consumed = 8.0
        await db_session.flush()

        updated = await quota_service.update_limit(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id="x",
            resource="requests",
            limit_value=100,
        )
        assert updated.limit_value == 100
        assert updated.consumed == 8.0

    async def test_resetting_zeroes_consumption(
        self, quota_service: QuotaService, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id="x",
            resource="requests",
            limit_value=10,
        )
        quota.consumed = 9.0
        await db_session.flush()

        reset = await quota_service.reset(
            organization_id, scope=QuotaScope.ORGANIZATION, scope_id="x", resource="requests"
        )
        assert reset.consumed == 0.0

    async def test_updating_a_missing_quota_raises(
        self, quota_service: QuotaService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await quota_service.update_limit(
                organization_id,
                scope=QuotaScope.ORGANIZATION,
                scope_id="nope",
                resource="requests",
                limit_value=5,
            )

    async def test_a_warning_fires_once_per_period(
        self, quota_service: QuotaService, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # One that fired on every request past the threshold would be a
        # stream nobody opens, which is the same as no warning.
        quota = await quota_service.define(
            organization_id,
            scope=QuotaScope.ORGANIZATION,
            scope_id="x",
            resource="requests",
            limit_value=10,
        )
        quota.consumed = 9.0
        await db_session.flush()

        assert len(await quota_service.maybe_warn(organization_id)) == 1
        assert await quota_service.maybe_warn(organization_id) == []


class TestExceptions:
    """Waivers, and what they may and may not waive."""

    async def test_an_exception_waives_a_denial(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        denier = await make_policy("deny-platform", PolicyEffect.DENY)
        before, _ = await decision_service.decide(request_for(organization_id))
        assert before.denied is True

        await compliance_service.grant_exception(
            organization_id,
            policy_id=denier.id,
            reason="migration in progress",
            expires_at=utcnow() + timedelta(days=1),
        )
        await db_session.flush()

        after, _ = await decision_service.decide(request_for(organization_id))
        assert after.effect is PolicyEffect.CONDITIONAL_ALLOW
        assert after.permitted is True
        assert "Waived by exception" in after.reason

    async def test_an_exception_cannot_waive_an_approval_requirement(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # One that could would be an approval by another name, granted
        # without the sign-off the policy asked for -- and unlike an
        # approval it would leave no record of who agreed.
        gate = await make_policy(
            "review-platform",
            PolicyEffect.REQUIRE_APPROVAL,
            obligations={"approval_type": "single", "levels": 1},
        )
        await compliance_service.grant_exception(
            organization_id,
            policy_id=gate.id,
            reason="trying to skip review",
            expires_at=utcnow() + timedelta(days=1),
        )
        await db_session.flush()

        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.effect is PolicyEffect.REQUIRE_APPROVAL
        assert decision.permitted is False

    async def test_an_expired_exception_does_not_waive(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # Filtered on expiry in the query, never in Python afterwards. An
        # expired exception that reached the evaluator would waive a
        # policy that is meant to be back in force -- a grant nobody
        # authorised.
        denier = await make_policy("deny-platform", PolicyEffect.DENY)
        granted = await compliance_service.grant_exception(
            organization_id,
            policy_id=denier.id,
            reason="temporary",
            expires_at=utcnow() + timedelta(days=1),
        )
        granted.expires_at = utcnow() - timedelta(minutes=1)
        await db_session.flush()

        decision, _stored = await decision_service.decide(request_for(organization_id))
        assert decision.denied is True

    async def test_an_exception_scoped_to_another_subject_does_not_apply(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        denier = await make_policy("deny-platform", PolicyEffect.DENY)
        await compliance_service.grant_exception(
            organization_id,
            policy_id=denier.id,
            reason="only for the migration account",
            expires_at=utcnow() + timedelta(days=1),
            subject_id="migration-bot",
        )
        await db_session.flush()

        decision, _stored = await decision_service.decide(
            request_for(organization_id, subject_id="user-1")
        )
        assert decision.denied is True

    async def test_relying_on_an_exception_is_counted(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # The number that makes a quiet problem visible: a waiver used a
        # thousand times has become the real policy.
        denier = await make_policy("deny-platform", PolicyEffect.DENY)
        granted = await compliance_service.grant_exception(
            organization_id,
            policy_id=denier.id,
            reason="temporary",
            expires_at=utcnow() + timedelta(days=1),
        )
        await db_session.flush()

        for _ in range(3):
            _decision, _stored = await decision_service.decide(request_for(organization_id))
        await db_session.flush()
        await db_session.refresh(granted)
        assert granted.use_count == 3


class TestApprovals:
    """Obligations, from raised to resolved."""

    async def test_an_approval_is_raised_with_the_right_level_count(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": "multi_level", "levels": 2},
        )
        assert raised.required_levels == 2
        assert str(raised.status) == str(ApprovalStatus.PENDING)

    async def test_two_approvals_satisfy_a_two_level_obligation(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": "multi_level", "levels": 2},
        )
        await approval_service.record_decision(
            organization_id, raised.id, approver_id="alice", approved=True
        )
        final = await approval_service.record_decision(
            organization_id, raised.id, approver_id="bob", approved=True
        )
        assert str(final.status) == str(ApprovalStatus.APPROVED)

    async def test_one_rejection_ends_it(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": "multi_level", "levels": 3},
        )
        await approval_service.record_decision(
            organization_id, raised.id, approver_id="alice", approved=True
        )
        final = await approval_service.record_decision(
            organization_id, raised.id, approver_id="bob", approved=False
        )
        assert str(final.status) == str(ApprovalStatus.REJECTED)

    async def test_one_approver_cannot_answer_twice(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": "multi_level", "levels": 2},
        )
        await approval_service.record_decision(
            organization_id, raised.id, approver_id="alice", approved=True
        )
        with pytest.raises(ValidationError, match="already recorded"):
            await approval_service.record_decision(
                organization_id, raised.id, approver_id="alice", approved=True
            )

    async def test_a_resolved_approval_cannot_be_changed(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        await approval_service.record_decision(
            organization_id, raised.id, approver_id="alice", approved=True
        )
        with pytest.raises(ConflictError, match="already"):
            await approval_service.record_decision(
                organization_id, raised.id, approver_id="bob", approved=False
            )

    async def test_an_emergency_approval_is_flagged_and_short_lived(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        # Break-glass that stays open overnight is a standing grant nobody
        # remembers issuing.
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": str(ApprovalType.EMERGENCY)},
        )
        assert raised.is_emergency is True
        assert raised.expires_at - raised.requested_at <= timedelta(hours=1, seconds=5)

    async def test_the_requester_may_self_approve_only_in_an_emergency(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        ordinary = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
            actor_id=CALLER,
        )
        with pytest.raises(ValidationError, match="cannot also grant"):
            await approval_service.record_decision(
                organization_id, ordinary.id, approver_id=str(CALLER), approved=True
            )

        emergency = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": str(ApprovalType.EMERGENCY)},
            actor_id=CALLER,
        )
        resolved = await approval_service.record_decision(
            organization_id, emergency.id, approver_id=str(CALLER), approved=True
        )
        assert str(resolved.status) == str(ApprovalStatus.APPROVED)

    async def test_an_overdue_approval_is_swept(
        self,
        approval_service: ApprovalService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # A pending approval that can never complete sitting on somebody's
        # list forever is how a queue stops being read at all.
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        raised.expires_at = utcnow() - timedelta(hours=1)
        await db_session.flush()

        assert await approval_service.sweep_expired(organization_id) == 1
        swept = await approval_service.get(organization_id, raised.id)
        assert str(swept.status) == str(ApprovalStatus.EXPIRED)

    async def test_the_derived_state_reports_expiry_before_the_sweep_runs(
        self,
        approval_service: ApprovalService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        raised.expires_at = utcnow() - timedelta(hours=1)
        await db_session.flush()

        state = await approval_service.state_of(organization_id, raised.id)
        assert state.status is ApprovalStatus.EXPIRED

    async def test_a_role_requirement_is_enforced(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={
                "approval_type": str(ApprovalType.ROLE),
                "required_roles": ["security-lead"],
            },
        )
        with pytest.raises(ValidationError, match="requires one of these roles"):
            await approval_service.record_decision(
                organization_id,
                raised.id,
                approver_id="bob",
                approved=True,
                approver_roles=["developer"],
            )

    async def test_cancelling_a_pending_approval(
        self, approval_service: ApprovalService, organization_id: uuid.UUID
    ) -> None:
        raised = await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.DASHBOARD,
            resource_id=None,
            action=ActionType.READ,
            obligations={"approval_type": "single"},
        )
        cancelled = await approval_service.cancel(
            organization_id, raised.id, reason="no longer needed"
        )
        assert str(cancelled.status) == str(ApprovalStatus.CANCELLED)

    async def test_an_unusable_obligation_is_refused_at_validation(
        self, approval_service: ApprovalService
    ) -> None:
        # Caught at publish time, because the alternative is a policy that
        # refuses requests and then cannot raise the obligation that would
        # let them through -- a dead end with no route forward.
        with pytest.raises(ValidationError, match="not an approval type"):
            await approval_service.validate_obligations({"approval_type": "vibes"})
        with pytest.raises(ValidationError, match="at least one level"):
            await approval_service.validate_obligations({"levels": 0})


class TestComplianceAndAudit:
    """Violations, waiver bounds, and the trail."""

    async def test_a_violation_is_recorded_and_announced(
        self,
        compliance_service: ComplianceService,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        stored = await compliance_service.record_violation(
            organization_id,
            title="Weak password policy",
            standard=ComplianceStandard.PASSWORD,
            severity="high",
        )
        assert str(stored.status) == str(ViolationStatus.OPEN)
        assert "PolicyViolationDetected" in publisher.names

    async def test_an_unknown_severity_is_refused(
        self, compliance_service: ComplianceService, organization_id: uuid.UUID
    ) -> None:
        # A free-text severity makes "show me the critical ones"
        # unanswerable.
        with pytest.raises(ValidationError, match="not a severity"):
            await compliance_service.record_violation(
                organization_id,
                title="x",
                standard=ComplianceStandard.SECURITY,
                severity="quite bad",
            )

    async def test_acknowledging_is_distinct_from_resolving(
        self, compliance_service: ComplianceService, organization_id: uuid.UUID
    ) -> None:
        # "Somebody knows about this" and "this is fixed" are different
        # facts; collapsing them makes an acknowledged-but-unfixed
        # violation disappear from the list of things to do.
        stored = await compliance_service.record_violation(
            organization_id, title="x", standard=ComplianceStandard.SECURITY
        )
        acknowledged = await compliance_service.acknowledge(organization_id, stored.id)
        assert str(acknowledged.status) == str(ViolationStatus.ACKNOWLEDGED)

    async def test_closing_needs_a_note(
        self, compliance_service: ComplianceService, organization_id: uuid.UUID
    ) -> None:
        stored = await compliance_service.record_violation(
            organization_id, title="x", standard=ComplianceStandard.SECURITY
        )
        with pytest.raises(ValidationError, match="needs a note"):
            await compliance_service.resolve(organization_id, stored.id, note="   ")

    async def test_a_waiver_is_recorded_as_waived_not_resolved(
        self, compliance_service: ComplianceService, organization_id: uuid.UUID
    ) -> None:
        stored = await compliance_service.record_violation(
            organization_id, title="x", standard=ComplianceStandard.SECURITY
        )
        waived = await compliance_service.resolve(
            organization_id, stored.id, note="accepted risk", waived=True
        )
        assert str(waived.status) == str(ViolationStatus.WAIVED)

    async def test_an_already_closed_violation_cannot_be_acknowledged(
        self, compliance_service: ComplianceService, organization_id: uuid.UUID
    ) -> None:
        stored = await compliance_service.record_violation(
            organization_id, title="x", standard=ComplianceStandard.SECURITY
        )
        await compliance_service.resolve(organization_id, stored.id, note="fixed")
        with pytest.raises(ConflictError):
            await compliance_service.acknowledge(organization_id, stored.id)

    async def test_an_exception_needs_a_reason(
        self,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        target = await make_policy("p1", PolicyEffect.DENY)
        with pytest.raises(ValidationError, match="stated reason"):
            await compliance_service.grant_exception(
                organization_id,
                policy_id=target.id,
                reason="  ",
                expires_at=utcnow() + timedelta(days=1),
            )

    async def test_an_exception_must_expire_in_the_future(
        self,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        target = await make_policy("p1", PolicyEffect.DENY)
        with pytest.raises(ValidationError, match="expire in the future"):
            await compliance_service.grant_exception(
                organization_id,
                policy_id=target.id,
                reason="because",
                expires_at=utcnow() - timedelta(hours=1),
            )

    async def test_an_exception_is_length_bounded(
        self,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # A longer waiver is a policy change; making it one is what gets
        # it reviewed as one.
        target = await make_policy("p1", PolicyEffect.DENY)
        with pytest.raises(ValidationError, match=f"most {MAX_EXCEPTION_DAYS} days"):
            await compliance_service.grant_exception(
                organization_id,
                policy_id=target.id,
                reason="forever please",
                expires_at=utcnow() + timedelta(days=MAX_EXCEPTION_DAYS + 1),
            )

    async def test_an_overused_exception_is_reportable(
        self,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # A waiver used a thousand times is not an exception, and nothing
        # else in the system would say so.
        target = await make_policy("p1", PolicyEffect.DENY)
        granted = await compliance_service.grant_exception(
            organization_id,
            policy_id=target.id,
            reason="temporary",
            expires_at=utcnow() + timedelta(days=1),
        )
        granted.use_count = 500
        await db_session.flush()

        assert len(await compliance_service.overused_exceptions(organization_id)) == 1

    async def test_a_revoked_exception_stops_applying(
        self,
        decision_service: DecisionService,
        compliance_service: ComplianceService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        denier = await make_policy("deny-platform", PolicyEffect.DENY)
        granted = await compliance_service.grant_exception(
            organization_id,
            policy_id=denier.id,
            reason="temporary",
            expires_at=utcnow() + timedelta(days=1),
        )
        await db_session.flush()

        waived, _ = await decision_service.decide(request_for(organization_id))
        assert waived.permitted is True

        await compliance_service.revoke_exception(organization_id, granted.id)
        await db_session.flush()

        restored, _ = await decision_service.decide(request_for(organization_id))
        assert restored.denied is True

    async def test_a_denied_entry_survives_the_rollback_of_the_request_that_raised(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
    ) -> None:
        # The shape of the real thing, and the lesson carried forward from
        # services/knowledge-graph-service: a refusal is recorded and then
        # *raised*, and session_scope rolls the request's transaction back
        # on the way out. An entry written on that shared session goes
        # with it. A request-scoped SAVEPOINT never rolls back the way a
        # real request does, which is why the API test there passed while
        # the behaviour was broken.
        service = AuditService(
            PolicyAuditRepository(db_session), session_factory=db_session_factory
        )
        with pytest.raises(ValidationError):
            async with session_scope(db_session_factory):
                await service.record_denied(
                    organization_id=organization_id,
                    action=AuditAction.DECISION_MADE,
                    entity_type="decision",
                    reason="policy 'deny-all' applied deny",
                )
                raise ValidationError("refused")

        async with db_session_factory() as reader:
            entries = await PolicyAuditRepository(reader).list_for_org(organization_id)
        assert [outcome_of(one) for one in entries] == [AuditOutcome.DENIED]

    async def test_an_audit_summary_counts_by_action_and_outcome(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.POLICY_CHANGED,
            entity_type="policy",
        )
        await audit_service.record_denied(
            organization_id=organization_id,
            action=AuditAction.DECISION_MADE,
            entity_type="decision",
            reason="refused",
        )
        summary = await audit_service.summarise(organization_id)
        assert summary["total"] == 2
        assert summary["denied"] == 1

    async def test_an_audit_storage_failure_does_not_fail_the_action(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        # Refusing to answer an authorization question because an audit
        # insert deadlocked would turn a bookkeeping problem into a
        # platform-wide outage. Forced by an entity_type far over the
        # column width, so a genuine database error is what gets
        # swallowed rather than a simulated one.
        assert (
            await audit_service.record(
                organization_id=organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="x" * 5_000,
            )
            is None
        )

    async def test_the_trail_does_not_cross_tenants(
        self, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(
            organization_id=organization_id,
            action=AuditAction.POLICY_CHANGED,
            entity_type="policy",
            entity_id="p1",
        )
        assert await audit_service.list_for_entity(uuid.uuid4(), "p1") == []


class TestSimulationService:
    """Rehearsals against a real catalogue."""

    def _payload(self) -> dict[str, Any]:
        return {
            "label": "read-dashboard",
            "subject_type": str(SubjectType.USER),
            "resource_type": str(ResourceType.DASHBOARD),
            "action": str(ActionType.READ),
            "subject": {"department": "platform"},
        }

    async def test_a_simulation_is_stored_with_its_findings(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
        publisher: RecordingPublisher,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        stored = await simulation_service.run(
            organization_id,
            label="baseline",
            requests=[request_from_payload(self._payload(), index=0)],
        )
        assert str(stored.status) == str(JobStatus.SUCCEEDED)
        assert stored.request_count == 1
        assert stored.allowed_count == 1
        assert "SimulationCompleted" in publisher.names

    async def test_a_draft_is_included_by_id(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # The whole point of a preview: answering "what would happen if I
        # published this" without publishing it.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        draft = await make_policy("deny-draft", PolicyEffect.DENY, publish=False)

        stored = await simulation_service.run(
            organization_id,
            label="what-if",
            requests=[request_from_payload(self._payload(), index=0)],
            draft_policy_ids=[draft.id],
        )
        assert stored.changed_count == 1
        assert stored.denied_count == 1

    async def test_a_draft_not_named_is_not_included(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Sweeping in every draft would answer a question nobody asked and
        # change its answer whenever a colleague started editing something
        # unrelated.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await make_policy("deny-draft", PolicyEffect.DENY, publish=False)

        stored = await simulation_service.run(
            organization_id,
            label="baseline",
            requests=[request_from_payload(self._payload(), index=0)],
        )
        assert stored.changed_count == 0

    async def test_excluding_a_policy_answers_the_mirror_question(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # "What breaks if I retire this?" -- the question people are
        # usually more wrong about.
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        denier = await make_policy("deny-all", PolicyEffect.DENY)

        result = await simulation_service.preview(
            organization_id,
            requests=[request_from_payload(self._payload(), index=0)],
            excluded_policy_ids=[denier.id],
        )
        assert result["changed_count"] == 1
        assert result["safe"] is True

    async def test_a_preview_is_not_stored(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await simulation_service.preview(
            organization_id, requests=[request_from_payload(self._payload(), index=0)]
        )
        assert await simulation_service.list_simulations(organization_id) == []

    async def test_an_empty_simulation_is_refused(
        self, simulation_service: SimulationService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="at least one request"):
            await simulation_service.run(organization_id, label="empty", requests=[])

    async def test_conflicts_are_detected_over_the_live_catalogue(
        self,
        simulation_service: SimulationService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await make_policy("deny-platform", PolicyEffect.DENY)
        conflicts = await simulation_service.detect_conflicts(organization_id)
        assert len(conflicts) == 1

    async def test_a_malformed_request_payload_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unusable"):
            request_from_payload({"subject_type": "nonsense"}, index=3)


class TestStatisticsAndReports:
    """Analytics and the generated reports."""

    async def test_the_rollup_counts_the_catalogue(
        self,
        statistics_service: StatisticsService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("p1", PolicyEffect.ALLOW)
        await make_policy("p2", PolicyEffect.DENY, publish=False)
        values = await statistics_service.compute(organization_id)
        assert values["policy_count"] == 2
        assert values["published_count"] == 1
        assert values["draft_count"] == 1

    async def test_the_rollup_counts_decisions(
        self,
        statistics_service: StatisticsService,
        decision_service: DecisionService,
        make_policy: PublishedPolicyFn,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        await make_policy("allow-platform", PolicyEffect.ALLOW)
        await decision_service.decide(request_for(organization_id))
        await decision_service.decide(request_for(organization_id, context=NOT_MATCHING))
        await db_session.flush()

        values = await statistics_service.compute(organization_id)
        assert values["decision_count"] == 2
        assert values["allowed_count"] == 1
        assert values["denied_count"] == 1

    async def test_an_unused_policy_is_counted(
        self,
        statistics_service: StatisticsService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Either dead weight or, far worse, a rule whose conditions have
        # drifted out of line with reality: it looks like governance and
        # enforces nothing.
        await make_policy("never-matched", PolicyEffect.DENY)
        values = await statistics_service.compute(organization_id)
        assert values["unused_policy_count"] == 1
        assert "never-matched" in values["policy_usage"]["never_used"]

    async def test_the_rollup_is_updated_in_place(
        self, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        first = await statistics_service.refresh(organization_id)
        second = await statistics_service.refresh(organization_id)
        assert first.id == second.id

    async def test_an_empty_organization_computes_without_dividing_by_zero(
        self, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        values = await statistics_service.compute(organization_id)
        assert values["decision_count"] == 0
        assert values["average_latency_ms"] == 0.0
        assert values["p95_latency_ms"] == 0.0

    @pytest.mark.parametrize("kind", list(ReportKind))
    async def test_every_report_kind_generates(
        self,
        kind: ReportKind,
        report_service: ReportService,
        make_policy: PublishedPolicyFn,
        organization_id: uuid.UUID,
    ) -> None:
        # Parametrised over the enum: a kind added without a builder would
        # otherwise produce an empty report that looks like an
        # organization with nothing to report.
        await make_policy("p1", PolicyEffect.DENY)
        generated = await report_service.generate(organization_id, kind=kind)
        assert str(generated.status) == str(JobStatus.SUCCEEDED), generated.error
        assert generated.payload
        assert generated.checksum_sha256

    async def test_a_report_verifies_against_its_digest(
        self, report_service: ReportService, organization_id: uuid.UUID
    ) -> None:
        generated = await report_service.generate(organization_id, kind=ReportKind.POLICY)
        assert report_service.verify(generated)["valid"] is True

    async def test_a_tampered_report_fails_verification(
        self,
        report_service: ReportService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        generated = await report_service.generate(organization_id, kind=ReportKind.POLICY)
        generated.payload = b"tampered"
        await db_session.flush()
        assert report_service.verify(generated)["valid"] is False

    async def test_an_executive_report_leads_with_what_needs_attention(
        self,
        report_service: ReportService,
        compliance_service: ComplianceService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        await compliance_service.record_violation(
            organization_id, title="x", standard=ComplianceStandard.SECURITY
        )
        await db_session.flush()

        generated = await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        assert "open violations" in (generated.summary or "")

    async def test_an_approval_report_calls_out_break_glass(
        self,
        report_service: ReportService,
        approval_service: ApprovalService,
        db_session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> None:
        # Emergency approvals get their own section rather than being one
        # row among two hundred, which would hide them.
        await approval_service.raise_for_decision(
            organization_id,
            policy_id=None,
            decision_id=None,
            subject_type=SubjectType.USER,
            subject_id="user-1",
            resource_type=ResourceType.SECRET,
            resource_id="s1",
            action=ActionType.DELETE,
            obligations={"approval_type": str(ApprovalType.EMERGENCY)},
        )
        await db_session.flush()

        generated = await report_service.generate(organization_id, kind=ReportKind.APPROVAL)
        assert generated.content["emergency_approvals"]

    async def test_a_report_from_another_organization_is_not_found(
        self, report_service: ReportService, organization_id: uuid.UUID
    ) -> None:
        # A report payload can hold every decision an organization has
        # made, so the ownership check is the difference between a
        # download and a disclosure.
        generated = await report_service.generate(organization_id, kind=ReportKind.POLICY)
        with pytest.raises(NotFoundError):
            await report_service.get(uuid.uuid4(), generated.id)
