"""Quotas, approvals, simulation, and the shipped guardrails.

All four are pure over their inputs, so all four are tested against
hand-built states whose correct answer is arithmetic rather than
opinion. Three properties get the most attention because each one is a
place where a plausible-looking implementation is wrong in a way nothing
surfaces:

- a quota limit of zero (unlimited, not "nothing allowed")
- an approval that was rejected and then expired (rejected)
- a simulation reporting what *breaks*, not what merely differs
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.validation import ValidationError

from app.approvals.engine import (
    ApproverDecision,
    decision_from_dict,
    expiry_for,
    required_levels,
    resolve,
    validate_approver,
)
from app.attributes.resolver import EvaluationContext
from app.evaluation.engine import EvaluablePolicy
from app.guardrails.builtin import BUILTIN_GUARDRAILS, guardrails_for
from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    AttributeSource,
    PolicyCategory,
    PolicyEffect,
    QuotaPeriod,
    ResourceType,
    RuleOperator,
    SubjectType,
)
from app.quotas.engine import (
    QuotaState,
    check,
    needs_reset,
    period_end,
    period_start,
)
from app.rules.engine import Condition, Rule, validate_rule
from app.simulation.engine import (
    SimulationRequest,
    detect_conflicts,
    impact_of,
    simulate,
)

NOW = datetime(2026, 7, 30, 14, 30, tzinfo=UTC)


def quota(
    limit: float,
    consumed: float,
    *,
    resource: str = "api_calls",
    period: QuotaPeriod = QuotaPeriod.MONTHLY,
    hard: bool = True,
    scope: str = "organization:acme",
) -> QuotaState:
    """A quota state, for arithmetic that is checkable by hand."""
    return QuotaState(
        scope=scope,
        resource=resource,
        limit_value=limit,
        consumed=consumed,
        period=period,
        is_hard_limit=hard,
        period_started_at=NOW.replace(day=1, hour=0, minute=0),
    )


def policy(
    slug: str,
    effect: PolicyEffect,
    *,
    path: str = "flag",
    value: object = True,
    priority: int = 100,
    resource_types: list[str] | None = None,
    actions: list[str] | None = None,
) -> EvaluablePolicy:
    """A policy matching on one attribute."""
    return EvaluablePolicy(
        policy_id=slug,
        slug=slug,
        name=slug,
        effect=effect,
        rule=Rule(
            name=slug,
            conditions=[
                Condition(
                    source=AttributeSource.SUBJECT,
                    path=path,
                    operator=RuleOperator.EQUALS,
                    value=value,
                )
            ],
        ),
        priority=priority,
        resource_types=resource_types or [],
        actions=actions or [],
    )


class TestQuotaArithmetic:
    """Headroom, ratios, and the zero-limit reading."""

    def test_headroom_is_what_is_left(self) -> None:
        assert quota(100, 40).remaining == 60

    def test_consumption_cannot_report_negative_headroom(self) -> None:
        assert quota(100, 150).remaining == 0

    def test_a_zero_limit_means_unlimited_not_forbidden(self) -> None:
        # Chosen deliberately: a quota row created without a limit -- by
        # a migration default, a partial form, a bad import -- would
        # otherwise refuse every request for that resource. An accidental
        # total outage is far worse than an accidental absence of
        # enforcement, and a genuine "nothing allowed" belongs in a DENY
        # policy where a refusal is visible.
        unlimited = quota(0, 5_000)
        assert unlimited.unlimited is True
        assert unlimited.exceeded is False
        assert unlimited.remaining == float("inf")
        assert unlimited.usage_ratio == 0.0

    def test_a_negative_limit_is_also_unlimited(self) -> None:
        assert quota(-1, 10).unlimited is True

    def test_exceeded_is_at_or_over_the_limit(self) -> None:
        assert quota(100, 99).exceeded is False
        assert quota(100, 100).exceeded is True
        assert quota(100, 101).exceeded is True

    def test_would_exceed_looks_ahead(self) -> None:
        # The check a request needs: not "am I over" but "would this put
        # me over".
        assert quota(100, 99).would_exceed(1) is False
        assert quota(100, 99).would_exceed(2) is True

    def test_the_dict_form_hides_infinity(self) -> None:
        # float('inf') is not JSON; an unlimited quota reports null.
        assert quota(0, 5).as_dict()["remaining"] is None
        assert quota(100, 5).as_dict()["remaining"] == 95


class TestQuotaPeriods:
    """When a period starts and ends."""

    @pytest.mark.parametrize(
        ("period", "expected"),
        [
            (QuotaPeriod.HOURLY, datetime(2026, 7, 30, 14, 0, tzinfo=UTC)),
            (QuotaPeriod.DAILY, datetime(2026, 7, 30, 0, 0, tzinfo=UTC)),
            (QuotaPeriod.WEEKLY, datetime(2026, 7, 27, 0, 0, tzinfo=UTC)),
            (QuotaPeriod.MONTHLY, datetime(2026, 7, 1, 0, 0, tzinfo=UTC)),
        ],
    )
    def test_a_period_starts_by_truncation(self, period: QuotaPeriod, expected: datetime) -> None:
        # Truncated rather than "24 hours after creation", so a daily
        # quota resets at midnight and two quotas created hours apart
        # reset together -- which is what an operator means by "daily".
        assert period_start(NOW, period) == expected

    def test_a_total_quota_never_resets(self) -> None:
        assert period_end(NOW, QuotaPeriod.TOTAL) is None
        assert needs_reset(quota(100, 50, period=QuotaPeriod.TOTAL), now=NOW) is False

    def test_a_month_is_calendar_aware(self) -> None:
        # Adding 30 days to 31 January lands in March and skips February
        # entirely, so a monthly quota would silently never reset in the
        # short month.
        january = datetime(2026, 1, 1, tzinfo=UTC)
        assert period_end(january, QuotaPeriod.MONTHLY) == datetime(2026, 2, 1, tzinfo=UTC)
        february = datetime(2026, 2, 1, tzinfo=UTC)
        assert period_end(february, QuotaPeriod.MONTHLY) == datetime(2026, 3, 1, tzinfo=UTC)

    def test_a_rolled_over_period_needs_a_reset(self) -> None:
        stale = QuotaState(
            scope="organization:acme",
            resource="api_calls",
            limit_value=100,
            consumed=100,
            period=QuotaPeriod.DAILY,
            is_hard_limit=True,
            period_started_at=NOW - timedelta(days=2),
        )
        assert needs_reset(stale, now=NOW) is True

    def test_a_current_period_does_not(self) -> None:
        current = QuotaState(
            scope="organization:acme",
            resource="api_calls",
            limit_value=100,
            consumed=10,
            period=QuotaPeriod.DAILY,
            is_hard_limit=True,
            period_started_at=period_start(NOW, QuotaPeriod.DAILY),
        )
        assert needs_reset(current, now=NOW) is False

    def test_a_naive_datetime_is_treated_as_utc(self) -> None:
        assert period_start(datetime(2026, 7, 30, 14, 30), QuotaPeriod.DAILY).tzinfo is UTC


class TestQuotaChecks:
    """Whether a request fits, and what it is told."""

    def test_headroom_permits(self) -> None:
        result = check([quota(100, 10)])
        assert result.permitted is True
        assert result.effect is PolicyEffect.ALLOW

    def test_no_quotas_permits(self) -> None:
        assert check([]).permitted is True

    def test_a_hard_limit_refuses_with_quota_exceeded(self) -> None:
        # A distinguishable refusal: "you are out of budget" needs a
        # different response from "you are not permitted".
        result = check([quota(100, 100)])
        assert result.permitted is False
        assert result.effect is PolicyEffect.QUOTA_EXCEEDED
        assert result.blocking is not None

    def test_a_soft_limit_warns_and_lets_through(self) -> None:
        # How a limit gets introduced without breaking the people already
        # over it.
        result = check([quota(100, 500, hard=False)])
        assert result.permitted is True
        assert any("soft" in one for one in result.warnings)

    def test_enforcement_can_be_switched_off_entirely(self) -> None:
        result = check([quota(100, 500)], enforcement_enabled=False)
        assert result.permitted is True
        assert any("not enforced" in one for one in result.warnings)

    def test_approaching_the_limit_warns_before_it_is_reached(self) -> None:
        # A quota that only speaks when exhausted gives an operator no
        # chance to act before work starts failing.
        result = check([quota(100, 80)], warning_threshold=0.8)
        assert result.permitted is True
        assert result.warnings
        assert "81%" in result.warnings[0]

    def test_every_blocking_quota_is_reported_not_just_the_first(self) -> None:
        # A caller told only about the first exhausted budget raises it,
        # retries, and hits the next one.
        result = check([quota(10, 10, resource="a"), quota(20, 20, resource="b")])
        assert result.permitted is False
        assert "1 other quota also blocked" in result.reason

    def test_the_tightest_quota_is_named_as_the_blocker(self) -> None:
        result = check([quota(1_000, 999, resource="loose"), quota(10, 10, resource="tight")])
        assert result.blocking is not None
        assert result.blocking.resource == "tight"

    def test_an_unlimited_quota_never_blocks(self) -> None:
        assert check([quota(0, 1_000_000)]).permitted is True

    def test_a_larger_amount_can_be_checked(self) -> None:
        assert check([quota(100, 95)], amount=10).permitted is False
        assert check([quota(100, 95)], amount=5).permitted is True

    def test_the_check_serialises(self) -> None:
        assert json.dumps(check([quota(100, 10)]).as_dict())


class TestApprovalLevels:
    """How many sign-offs a request needs."""

    def test_a_single_approval_needs_one(self) -> None:
        assert required_levels(ApprovalType.SINGLE) == 1

    def test_multi_level_needs_at_least_two(self) -> None:
        # Declaring "multi-level, one approver" is a contradiction; the
        # floor is what makes the type mean something.
        assert required_levels(ApprovalType.MULTI_LEVEL, declared=1) == 2
        assert required_levels(ApprovalType.MULTI_LEVEL, declared=4) == 4

    def test_automatic_needs_none(self) -> None:
        assert required_levels(ApprovalType.AUTOMATIC) == 0

    @pytest.mark.parametrize(
        ("risk", "expected"), [(0.1, 1), (0.5, 2), (0.79, 2), (0.8, 3), (1.0, 3)]
    )
    def test_risk_based_scales_with_risk(self, risk: float, expected: int) -> None:
        # The only type that computes rather than reads: a routine change
        # needs one sign-off and a dangerous one needs three, without an
        # author enumerating the bands.
        assert required_levels(ApprovalType.RISK_BASED, risk_score=risk) == expected

    def test_emergency_is_one_self_approval(self) -> None:
        # What makes break-glass acceptable is not scarcity of approvers
        # but that it is flagged, audited, and notified every time.
        assert required_levels(ApprovalType.EMERGENCY) == 1


class TestApprovalResolution:
    """What a set of answers means."""

    def _decision(self, who: str, approved: bool) -> ApproverDecision:
        return ApproverDecision(approver_id=who, approved=approved, decided_at=NOW)

    def test_enough_approvals_approves(self) -> None:
        state = resolve(
            [self._decision("a", True), self._decision("b", True)],
            required=2,
            expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.APPROVED
        assert state.remaining == 0

    def test_too_few_stays_pending(self) -> None:
        state = resolve(
            [self._decision("a", True)],
            required=3,
            expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.PENDING
        assert state.remaining == 2

    def test_one_rejection_ends_it(self) -> None:
        # Waiting for a third opinion after someone has objected turns a
        # veto into a vote, which is not what an approval gate is.
        state = resolve(
            [self._decision("a", True), self._decision("b", False)],
            required=3,
            expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.REJECTED

    def test_a_rejection_names_who_rejected(self) -> None:
        state = resolve(
            [
                ApproverDecision("carol", False, NOW, comment="not during freeze"),
            ],
            required=1,
            expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
        assert "carol" in state.reason
        assert "not during freeze" in state.reason

    def test_a_rejected_and_expired_approval_is_rejected(self) -> None:
        # The objection is the fact worth recording; reporting "expired"
        # would lose why nobody acted on it.
        state = resolve(
            [self._decision("a", False)],
            required=1,
            expires_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.REJECTED

    def test_the_deadline_does_not_undo_a_completed_approval(self) -> None:
        # Sufficiency is checked before expiry, so an approval whose last
        # sign-off landed a second before the deadline is approved rather
        # than lost to a clock.
        state = resolve(
            [self._decision("a", True)],
            required=1,
            expires_at=NOW - timedelta(seconds=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.APPROVED

    def test_an_incomplete_approval_expires(self) -> None:
        state = resolve(
            [self._decision("a", True)],
            required=2,
            expires_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        assert state.status is ApprovalStatus.EXPIRED
        assert state.remaining == 1

    def test_no_decisions_at_all_is_pending(self) -> None:
        state = resolve([], required=1, expires_at=NOW + timedelta(hours=1), now=NOW)
        assert state.status is ApprovalStatus.PENDING

    def test_a_state_serialises(self) -> None:
        state = resolve(
            [self._decision("a", True)],
            required=1,
            expires_at=NOW + timedelta(hours=1),
            now=NOW,
        )
        assert json.dumps(state.as_dict())


class TestApproverValidation:
    """Who may answer."""

    def test_an_approver_cannot_answer_twice(self) -> None:
        # Multi-level approval exists so several people look at
        # something; one person satisfying every level makes the
        # requirement decorative.
        existing = [ApproverDecision("alice", True, NOW)]
        with pytest.raises(ValidationError, match="already recorded"):
            validate_approver(
                "alice",
                decisions=existing,
                required_roles=[],
                approver_roles=[],
                requested_by=None,
                allow_self_approval=True,
            )

    def test_a_required_role_is_enforced(self) -> None:
        with pytest.raises(ValidationError, match="requires one of these roles"):
            validate_approver(
                "bob",
                decisions=[],
                required_roles=["security-lead"],
                approver_roles=["developer"],
                requested_by=None,
                allow_self_approval=True,
            )

    def test_holding_any_required_role_is_enough(self) -> None:
        validate_approver(
            "bob",
            decisions=[],
            required_roles=["security-lead", "platform-lead"],
            approver_roles=["platform-lead"],
            requested_by=None,
            allow_self_approval=True,
        )

    def test_the_requester_cannot_approve_their_own_request(self) -> None:
        with pytest.raises(ValidationError, match="cannot also grant"):
            validate_approver(
                "alice",
                decisions=[],
                required_roles=[],
                approver_roles=[],
                requested_by="alice",
                allow_self_approval=False,
            )

    def test_self_approval_is_allowed_for_emergencies(self) -> None:
        validate_approver(
            "alice",
            decisions=[],
            required_roles=[],
            approver_roles=[],
            requested_by="alice",
            allow_self_approval=True,
        )


class TestApprovalExpiry:
    """How long an obligation stays actionable."""

    def test_an_ordinary_approval_uses_the_configured_window(self) -> None:
        assert expiry_for(ApprovalType.SINGLE, hours=48, now=NOW) == NOW + timedelta(hours=48)

    def test_an_emergency_approval_expires_fast(self) -> None:
        # Break-glass that stays open overnight is a standing grant
        # nobody remembers issuing.
        assert expiry_for(ApprovalType.EMERGENCY, hours=48, now=NOW) == NOW + timedelta(hours=1)

    def test_a_stored_decision_round_trips(self) -> None:
        original = ApproverDecision("alice", True, NOW, comment="ok", roles=("lead",))
        rebuilt = decision_from_dict(original.as_dict())
        assert rebuilt.approver_id == "alice"
        assert rebuilt.approved is True
        assert rebuilt.roles == ("lead",)

    def test_a_decision_with_no_timestamp_still_rebuilds(self) -> None:
        rebuilt = decision_from_dict({"approver_id": "a", "approved": True})
        assert rebuilt.decided_at.tzinfo is not None


class TestSimulation:
    """Rehearsing a change before it is live."""

    def _requests(self) -> list[SimulationRequest]:
        return [
            SimulationRequest(
                label="read-dashboard",
                subject_type=SubjectType.USER,
                resource_type=ResourceType.DASHBOARD,
                action=ActionType.READ,
                context=EvaluationContext(subject={"flag": True}),
            )
        ]

    def test_an_unchanged_catalogue_changes_nothing(self) -> None:
        catalogue = [policy("allow", PolicyEffect.ALLOW)]
        result = simulate(catalogue, catalogue, self._requests())
        assert result.changed_count == 0
        assert result.allowed_count == 1

    def test_adding_a_deny_is_reported_as_a_change(self) -> None:
        baseline = [policy("allow", PolicyEffect.ALLOW)]
        candidate = [*baseline, policy("deny", PolicyEffect.DENY)]
        result = simulate(baseline, candidate, self._requests())
        assert result.changed_count == 1
        assert result.denied_count == 1

    def test_newly_denied_is_separated_from_merely_changed(self) -> None:
        # The single most important thing a preview can report: a change
        # that turns allows into denies breaks people.
        baseline = [policy("allow", PolicyEffect.ALLOW)]
        candidate = [*baseline, policy("deny", PolicyEffect.DENY)]
        result = simulate(baseline, candidate, self._requests())
        assert len(result.newly_denied) == 1
        assert result.newly_denied[0].newly_denied is True

    def test_newly_permitted_is_recognised_too(self) -> None:
        baseline = [policy("deny", PolicyEffect.DENY)]
        candidate = [policy("allow", PolicyEffect.ALLOW)]
        result = simulate(baseline, candidate, self._requests())
        assert result.outcomes[0].newly_permitted is True

    def test_an_approval_requirement_counts_as_newly_denied(self) -> None:
        # It is not a permit, so something that used to work now needs a
        # human -- which is exactly the kind of break a preview is for.
        baseline = [policy("allow", PolicyEffect.ALLOW)]
        candidate = [*baseline, policy("review", PolicyEffect.REQUIRE_APPROVAL)]
        result = simulate(baseline, candidate, self._requests())
        assert len(result.newly_denied) == 1

    def test_the_summary_leads_with_what_breaks(self) -> None:
        baseline = [policy("allow", PolicyEffect.ALLOW)]
        candidate = [*baseline, policy("deny", PolicyEffect.DENY)]
        assert (
            "would newly be refused" in simulate(baseline, candidate, self._requests()).summarise()
        )

    def test_an_empty_simulation_says_so(self) -> None:
        assert "No requests" in simulate([], [], []).summarise()

    def test_impact_analysis_flags_whether_a_change_is_safe(self) -> None:
        baseline = [policy("allow", PolicyEffect.ALLOW)]
        safe = impact_of(baseline, baseline, self._requests())
        assert safe["safe"] is True

        breaking = impact_of(
            baseline, [*baseline, policy("deny", PolicyEffect.DENY)], self._requests()
        )
        assert breaking["safe"] is False
        assert breaking["breaking_changes"]

    def test_a_result_serialises(self) -> None:
        assert json.dumps(
            simulate([policy("a", PolicyEffect.ALLOW)], [], self._requests()).as_dict()
        )


class TestConflictDetection:
    """Which policy pairs are worth a human look."""

    def test_opposing_effects_on_a_shared_attribute_conflict(self) -> None:
        conflicts = detect_conflicts(
            [policy("allow", PolicyEffect.ALLOW), policy("deny", PolicyEffect.DENY)]
        )
        assert len(conflicts) == 1
        assert set(conflicts[0]["policies"]) == {"allow", "deny"}

    def test_the_resolution_says_which_would_win(self) -> None:
        conflicts = detect_conflicts(
            [policy("allow", PolicyEffect.ALLOW), policy("deny", PolicyEffect.DENY)]
        )
        assert "deny" in conflicts[0]["resolution"]

    def test_two_allows_do_not_conflict(self) -> None:
        # Opposing effects alone would flag every allow/deny pair in the
        # catalogue, which is most of it.
        assert (
            detect_conflicts([policy("a", PolicyEffect.ALLOW), policy("b", PolicyEffect.ALLOW)])
            == []
        )

    def test_disjoint_attributes_cannot_disagree(self) -> None:
        # What makes the analysis cheap: two policies reading different
        # attributes cannot contradict each other on one request.
        assert (
            detect_conflicts(
                [
                    policy("allow", PolicyEffect.ALLOW, path="department"),
                    policy("deny", PolicyEffect.DENY, path="clearance"),
                ]
            )
            == []
        )

    def test_non_overlapping_selectors_cannot_conflict(self) -> None:
        assert (
            detect_conflicts(
                [
                    policy(
                        "allow",
                        PolicyEffect.ALLOW,
                        resource_types=[str(ResourceType.DASHBOARD)],
                    ),
                    policy("deny", PolicyEffect.DENY, resource_types=[str(ResourceType.SECRET)]),
                ]
            )
            == []
        )

    def test_an_empty_selector_overlaps_everything(self) -> None:
        conflicts = detect_conflicts(
            [
                policy("blanket-deny", PolicyEffect.DENY),
                policy(
                    "narrow-allow",
                    PolicyEffect.ALLOW,
                    resource_types=[str(ResourceType.DASHBOARD)],
                ),
            ]
        )
        assert len(conflicts) == 1

    def test_a_conflict_is_reported_as_potential_not_certain(self) -> None:
        # Proving two rule trees can both be satisfied is a
        # satisfiability problem; claiming more certainty than the
        # analysis has would be dishonest.
        conflicts = detect_conflicts(
            [policy("allow", PolicyEffect.ALLOW), policy("deny", PolicyEffect.DENY)]
        )
        assert "Potential conflict" in conflicts[0]["note"]

    def test_the_shared_attributes_are_named(self) -> None:
        conflicts = detect_conflicts(
            [policy("allow", PolicyEffect.ALLOW), policy("deny", PolicyEffect.DENY)]
        )
        assert conflicts[0]["shared_attributes"] == ["subject.flag"]


class TestBuiltinGuardrails:
    """The policies a fresh organization starts with."""

    def test_every_guardrail_has_a_valid_rule(self) -> None:
        # These ship with the product. One that will not compile is a
        # deployment that fails to seed, found here rather than on a
        # customer's first boot.
        for template in BUILTIN_GUARDRAILS:
            validate_rule(template.rule)

    def test_slugs_are_unique(self) -> None:
        slugs = [one.slug for one in BUILTIN_GUARDRAILS]
        assert len(slugs) == len(set(slugs))

    def test_secrets_may_not_be_exported(self) -> None:
        # There is no configuration under which exporting a secret is the
        # right operation, so it is refused rather than gated.
        template = next(one for one in BUILTIN_GUARDRAILS if one.slug == "deny-secret-export")
        assert template.effect is PolicyEffect.DENY
        assert str(ActionType.EXPORT) in template.actions

    def test_unauthenticated_requests_are_denied(self) -> None:
        # Without this, an unauthenticated request is merely one whose
        # subject attributes are missing, and a policy written in terms
        # of what a subject *is* would not notice.
        template = next(
            one for one in BUILTIN_GUARDRAILS if one.slug == "deny-expired-authentication"
        )
        assert template.effect is PolicyEffect.DENY
        assert template.priority >= 1_000

    def test_production_deletes_are_gated_rather_than_refused(self) -> None:
        # A legitimate thing to do, just not alone and not by accident.
        template = next(
            one for one in BUILTIN_GUARDRAILS if one.slug == "require-approval-production-delete"
        )
        assert template.effect is PolicyEffect.REQUIRE_APPROVAL
        assert template.obligations["levels"] == 1

    def test_the_set_stays_small(self) -> None:
        # A long list of shipped policies is a list somebody disables
        # wholesale the first time one gets in the way -- and the whole
        # set goes with it.
        assert len(BUILTIN_GUARDRAILS) <= 10

    def test_guardrails_can_be_filtered_by_category(self) -> None:
        security = guardrails_for(PolicyCategory.SECURITY)
        assert security
        assert all(one.category is PolicyCategory.SECURITY for one in security)
        assert len(guardrails_for()) == len(BUILTIN_GUARDRAILS)
