"""The assessment engine, the scorer, and risk arithmetic.

All three are pure. Between them they decide what an organization is
told about its own compliance posture, so the tests here are mostly
about the answers that are *tempting and wrong*: passing a control
nobody could measure, scoring an estate nobody inspected, and letting a
risk owner grade their own risk.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.assessments.engine import (
    AssessmentOutcome,
    ControlResult,
    EvaluableControl,
    Target,
    Waiver,
    evaluate_assessment,
    evaluate_control,
    finding_severity_for,
    target_id_of,
)
from app.frameworks.builtin import (
    BUILTIN_FRAMEWORKS,
    BUILTIN_MAPPINGS,
    all_evidence_paths,
    framework_by_slug,
)
from app.models.enums import (
    ControlSeverity,
    ControlStatus,
    FindingSeverity,
    ResultStatus,
    RiskImpact,
    RiskLikelihood,
    RiskSeverity,
    ScoreGrade,
    grade_for,
    severity_for,
)
from app.risk.engine import (
    assess,
    due_at,
    fingerprint,
    is_overdue,
    next_reference,
    next_review,
    residual,
    risk_score_for_finding,
)
from app.rules.engine import Check, CheckOperator, Rule, validate_rule
from app.scoring.engine import (
    ScoredResult,
    combine_framework_scores,
    compute_score,
    coverage_of,
    delta_of,
    score_by_framework,
    score_by_target,
    trend_of,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def control(
    *,
    code: str = "C-1",
    severity: ControlSeverity = ControlSeverity.HIGH,
    status: ControlStatus = ControlStatus.IMPLEMENTED,
    automatable: bool = True,
    rule: Rule | None = None,
) -> EvaluableControl:
    return EvaluableControl(
        control_id=f"control-{code}",
        framework_id="framework-1",
        code=code,
        title=f"Control {code}",
        severity=severity,
        status=status,
        is_automatable=automatable,
        rule=(
            rule
            if rule is not None
            else Rule(
                name=code, checks=[Check(path="firewall.enabled", operator=CheckOperator.IS_TRUE)]
            )
        ),
    )


def scored(
    status: ResultStatus,
    severity: ControlSeverity = ControlSeverity.HIGH,
    *,
    framework_id: str | None = "f1",
    target_id: str | None = "host-1",
    control_id: str = "c1",
) -> ScoredResult:
    return ScoredResult(
        control_id=control_id,
        status=status,
        severity=severity,
        framework_id=framework_id,
        target_id=target_id,
    )


class TestControlEvaluation:
    def test_a_met_control_passes(self) -> None:
        result = evaluate_control(
            control(), Target("host-1", "server", payload={"firewall": {"enabled": True}}), now=NOW
        )
        assert result.status is ResultStatus.PASS

    def test_an_unmet_control_fails_and_says_why(self) -> None:
        result = evaluate_control(
            control(), Target("host-1", "server", payload={"firewall": {"enabled": False}}), now=NOW
        )
        assert result.status is ResultStatus.FAIL
        assert "firewall.enabled" in result.reason

    def test_a_control_with_no_evidence_is_not_assessed_never_passed(self) -> None:
        # The single most important assertion in this file. A collector
        # that silently returned nothing must not certify the host it
        # failed to reach -- defaulting to pass here is how compliance
        # tools come to report green estates they never inspected.
        result = evaluate_control(control(), Target("host-1", "server", payload={}), now=NOW)
        assert result.status is ResultStatus.NOT_ASSESSED
        assert result.status is not ResultStatus.PASS
        assert "No evidence" in result.reason

    def test_a_manual_control_is_not_assessed_never_passed(self) -> None:
        # A control that needs somebody to read a policy document cannot
        # be satisfied by a scanner that found nothing to complain about.
        result = evaluate_control(
            control(automatable=False),
            Target("host-1", "server", payload={"firewall": {"enabled": True}}),
            now=NOW,
        )
        assert result.status is ResultStatus.NOT_ASSESSED
        assert "not automatable" in result.reason

    def test_a_control_marked_automatable_with_no_rule_is_not_assessed(self) -> None:
        # Flagged automatable but carrying no rule: a half-configured
        # control must not be reported as met.
        ruleless = EvaluableControl(
            control_id="c",
            framework_id=None,
            code="C-9",
            title="Half-configured",
            severity=ControlSeverity.HIGH,
            status=ControlStatus.IMPLEMENTED,
            is_automatable=True,
            rule=None,
        )
        result = evaluate_control(ruleless, Target("host-1", "server", payload={"a": 1}), now=NOW)
        assert result.status is ResultStatus.NOT_ASSESSED

    def test_a_scoped_out_control_is_not_applicable_and_short_circuits(self) -> None:
        # Checked before evidence, because a control an organization has
        # formally scoped out is not a requirement -- it must leave the
        # denominator entirely rather than sitting in it as an unknown.
        result = evaluate_control(
            control(status=ControlStatus.NOT_APPLICABLE),
            Target("host-1", "server", payload={}),
            now=NOW,
        )
        assert result.status is ResultStatus.NOT_APPLICABLE

    def test_a_failing_informational_control_warns_rather_than_fails(self) -> None:
        # It still produces a finding; it simply must not turn a
        # dashboard red, because that trains people to ignore red.
        result = evaluate_control(
            control(severity=ControlSeverity.INFORMATIONAL),
            Target("host-1", "server", payload={"firewall": {"enabled": False}}),
            now=NOW,
        )
        assert result.status is ResultStatus.WARNING
        assert result.is_failure is True


class TestWaivers:
    def test_an_active_waiver_excepts_a_failure_and_is_disclosed(self) -> None:
        result = evaluate_control(
            control(),
            Target("host-1", "server", payload={"firewall": {"enabled": False}}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", "host-1", NOW + timedelta(days=30))],
        )
        assert result.status is ResultStatus.EXCEPTED
        assert result.exception_id == "ex-1"
        assert "ex-1" in result.reason

    def test_an_expired_waiver_does_not_except(self) -> None:
        result = evaluate_control(
            control(),
            Target("host-1", "server", payload={"firewall": {"enabled": False}}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", "host-1", NOW - timedelta(days=1))],
        )
        assert result.status is ResultStatus.FAIL

    def test_a_waiver_for_another_target_does_not_except(self) -> None:
        result = evaluate_control(
            control(),
            Target("host-1", "server", payload={"firewall": {"enabled": False}}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", "host-2", None)],
        )
        assert result.status is ResultStatus.FAIL

    def test_a_waiver_with_no_target_covers_every_target(self) -> None:
        result = evaluate_control(
            control(),
            Target("host-99", "server", payload={"firewall": {"enabled": False}}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", None, None)],
        )
        assert result.status is ResultStatus.EXCEPTED

    def test_a_waiver_never_turns_a_pass_into_an_exception(self) -> None:
        result = evaluate_control(
            control(),
            Target("host-1", "server", payload={"firewall": {"enabled": True}}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", None, None)],
        )
        assert result.status is ResultStatus.PASS
        assert result.exception_id is None

    def test_a_waiver_never_excuses_an_unassessed_control(self) -> None:
        # Waiving "we could not measure this" would hide a broken
        # collector behind a business decision, and the two need
        # different people to look at them.
        result = evaluate_control(
            control(),
            Target("host-1", "server", payload={}),
            now=NOW,
            waivers=[Waiver("ex-1", "control-C-1", None, None)],
        )
        assert result.status is ResultStatus.NOT_ASSESSED
        assert result.exception_id is None


class TestAssessmentRuns:
    def test_every_control_meets_every_target(self) -> None:
        outcome = evaluate_assessment(
            [control(code="A"), control(code="B")],
            [
                Target("h1", "server", payload={"firewall": {"enabled": True}}),
                Target("h2", "server", payload={"firewall": {"enabled": False}}),
            ],
            now=NOW,
        )
        assert len(outcome.results) == 4
        assert outcome.counts()[str(ResultStatus.PASS)] == 2
        assert outcome.counts()[str(ResultStatus.FAIL)] == 2

    def test_a_control_with_no_targets_still_produces_a_verdict(self) -> None:
        # An organization-wide control ("an incident response plan
        # exists") must not vanish because the estate list was empty.
        outcome = evaluate_assessment([control()], [], now=NOW)
        assert len(outcome.results) == 1
        assert outcome.results[0].target_type == "organization"

    def test_the_control_ceiling_truncates_and_says_so(self) -> None:
        outcome = evaluate_assessment(
            [control(code=f"C{i}") for i in range(10)],
            [Target("h1", "server", payload={"firewall": {"enabled": True}})],
            now=NOW,
            max_controls=3,
        )
        assert outcome.controls_evaluated == 3
        assert outcome.truncated is True
        assert "10 controls" in (outcome.truncation_reason or "")

    def test_the_target_ceiling_truncates_and_says_so(self) -> None:
        outcome = evaluate_assessment(
            [control()],
            [Target(f"h{i}", "server", payload={"firewall": {"enabled": True}}) for i in range(10)],
            now=NOW,
            max_targets_per_control=4,
        )
        assert len(outcome.results) == 4
        assert outcome.truncated is True
        assert "10 targets" in (outcome.truncation_reason or "")

    def test_both_ceilings_report_together(self) -> None:
        # Either ceiling alone can be satisfied while the product is
        # still ruinous, so both have to be reportable at once.
        outcome = evaluate_assessment(
            [control(code=f"C{i}") for i in range(5)],
            [Target(f"h{i}", "server", payload={"a": 1}) for i in range(5)],
            now=NOW,
            max_controls=2,
            max_targets_per_control=2,
        )
        assert "controls" in (outcome.truncation_reason or "")
        assert "targets" in (outcome.truncation_reason or "")

    def test_an_untruncated_run_says_nothing_about_truncation(self) -> None:
        outcome = evaluate_assessment([control()], [Target("h", "s", payload={"a": 1})], now=NOW)
        assert outcome.truncated is False
        assert outcome.truncation_reason is None

    def test_failures_are_what_becomes_findings(self) -> None:
        outcome = evaluate_assessment(
            [control(code="A"), control(code="B", severity=ControlSeverity.INFORMATIONAL)],
            [Target("h1", "server", payload={"firewall": {"enabled": False}})],
            now=NOW,
        )
        # A fail and a warning: both raise findings, at different
        # severities.
        assert len(outcome.failures()) == 2

    def test_counts_covers_every_status_even_at_zero(self) -> None:
        # A report reading `counts()["error"]` must not KeyError just
        # because nothing errored.
        counts = AssessmentOutcome().counts()
        assert set(counts) == {str(one) for one in ResultStatus}
        assert all(value == 0 for value in counts.values())

    def test_a_result_is_json_serialisable(self) -> None:
        result = ControlResult(
            control_id="c", framework_id=None, status=ResultStatus.PASS, reason="ok"
        )
        assert json.dumps(result.as_dict())

    def test_target_id_of_normalises(self) -> None:
        value = uuid.uuid4()
        assert target_id_of(value) == str(value)
        assert target_id_of(None) is None
        assert target_id_of("x") == "x"

    def test_finding_severity_tracks_control_severity(self) -> None:
        assert finding_severity_for(ControlSeverity.CRITICAL) is FindingSeverity.CRITICAL
        assert finding_severity_for(ControlSeverity.INFORMATIONAL) is FindingSeverity.INFORMATIONAL


class TestScoring:
    def test_an_all_passing_set_scores_one_hundred(self) -> None:
        assert compute_score([scored(ResultStatus.PASS)] * 4).score == 100.0

    def test_an_all_failing_set_scores_zero(self) -> None:
        assert compute_score([scored(ResultStatus.FAIL)] * 4).score == 0.0

    def test_severity_weighting_beats_a_raw_pass_rate(self) -> None:
        # Nine passing low controls and one failing critical is 90% by
        # count. Weighted, the critical dominates -- which is the whole
        # reason unweighted compliance percentages are worth so little.
        results = [scored(ResultStatus.PASS, ControlSeverity.LOW) for _ in range(9)]
        results.append(scored(ResultStatus.FAIL, ControlSeverity.CRITICAL))
        breakdown = compute_score(results)
        assert breakdown.raw_pass_rate == 90.0
        assert breakdown.weighted_score < 50.0

    def test_an_informational_control_carries_no_weight(self) -> None:
        # A hundred passing informational controls must not drown out
        # one failing critical one.
        results = [scored(ResultStatus.PASS, ControlSeverity.INFORMATIONAL) for _ in range(100)]
        results.append(scored(ResultStatus.FAIL, ControlSeverity.CRITICAL))
        assert compute_score(results).weighted_score == 0.0

    def test_an_entirely_informational_set_falls_back_to_the_raw_rate(self) -> None:
        # Total weight is zero, so the weighted score is undefined.
        # Reporting 0% would say "totally non-compliant" about an estate
        # whose only findings are advisory.
        results = [scored(ResultStatus.PASS, ControlSeverity.INFORMATIONAL) for _ in range(3)]
        results.append(scored(ResultStatus.WARNING, ControlSeverity.INFORMATIONAL))
        breakdown = compute_score(results)
        assert breakdown.weighted_score == 75.0
        assert breakdown.raw_pass_rate == 75.0

    def test_an_excepted_control_counts_as_satisfied(self) -> None:
        # A documented, approved, expiring acceptance of a specific
        # risk. Treating it as a failure would mean an organization that
        # governs its exceptions properly scores worse than one that
        # never files any -- exactly backwards.
        breakdown = compute_score([scored(ResultStatus.EXCEPTED), scored(ResultStatus.PASS)])
        assert breakdown.score == 100.0
        assert breakdown.excepted == 1

    def test_exceptions_are_reported_separately_so_the_loophole_is_visible(self) -> None:
        results = [scored(ResultStatus.EXCEPTED) for _ in range(4)]
        results.append(scored(ResultStatus.PASS))
        breakdown = compute_score(results)
        assert breakdown.score == 100.0
        assert breakdown.excepted == 4, "'94% and 40% of it is waivers' must be a sayable sentence"

    @pytest.mark.parametrize(
        "status", [ResultStatus.NOT_APPLICABLE, ResultStatus.NOT_ASSESSED, ResultStatus.ERROR]
    )
    def test_unmeasured_controls_leave_the_denominator(self, status: ResultStatus) -> None:
        # Scoring unknowns as failures makes a partial run look like a
        # catastrophe; scoring them as passes makes it look like a
        # success. Both are lies.
        breakdown = compute_score([scored(ResultStatus.PASS), scored(status)])
        assert breakdown.total == 1
        assert breakdown.score == 100.0

    def test_a_score_from_too_little_data_is_not_publishable(self) -> None:
        # A framework with one assessed control out of three hundred can
        # report 100%, and that number *will* be quoted.
        breakdown = compute_score([scored(ResultStatus.PASS)], minimum_controls=10)
        assert breakdown.score == 100.0
        assert breakdown.publishable is False
        assert "at least 10" in (breakdown.suppression_reason or "")

    def test_an_empty_set_scores_zero_without_dividing_by_zero(self) -> None:
        breakdown = compute_score([])
        assert breakdown.score == 0.0
        assert breakdown.total == 0

    def test_the_breakdown_reports_each_severity_band(self) -> None:
        # An 87% of low-severity failures and an 87% of three failing
        # criticals are the same number and different situations.
        results = [
            scored(ResultStatus.PASS, ControlSeverity.CRITICAL),
            scored(ResultStatus.FAIL, ControlSeverity.LOW),
            scored(ResultStatus.NOT_ASSESSED, ControlSeverity.HIGH),
        ]
        bands = compute_score(results).by_severity
        assert bands["critical"]["passed"] == 1
        assert bands["low"]["failed"] == 1
        assert bands["high"]["other"] == 1

    def test_the_breakdown_is_json_serialisable(self) -> None:
        assert json.dumps(compute_score([scored(ResultStatus.PASS)]).as_dict())

    def test_coverage_is_reported_beside_the_score(self) -> None:
        # A 100% score across 4% coverage is not compliance.
        results = [scored(ResultStatus.PASS)] + [scored(ResultStatus.NOT_ASSESSED)] * 24
        assert compute_score(results).score == 100.0
        assert coverage_of(results) == 4.0

    def test_coverage_excludes_scoped_out_controls_from_both_halves(self) -> None:
        results = [scored(ResultStatus.PASS), scored(ResultStatus.NOT_APPLICABLE)]
        assert coverage_of(results) == 100.0

    def test_coverage_of_nothing_is_zero_not_a_crash(self) -> None:
        assert coverage_of([]) == 0.0
        assert coverage_of([scored(ResultStatus.NOT_APPLICABLE)]) == 0.0

    def test_scores_group_by_framework(self) -> None:
        results = [
            scored(ResultStatus.PASS, framework_id="f1"),
            scored(ResultStatus.FAIL, framework_id="f2"),
            scored(ResultStatus.PASS, framework_id=None),
        ]
        by_framework = score_by_framework(results)
        assert set(by_framework) == {"f1", "f2"}
        assert by_framework["f1"].score == 100.0
        assert by_framework["f2"].score == 0.0

    def test_scores_group_by_target(self) -> None:
        results = [
            scored(ResultStatus.PASS, target_id="h1"),
            scored(ResultStatus.FAIL, target_id="h2"),
            scored(ResultStatus.PASS, target_id=None),
        ]
        assert set(score_by_target(results)) == {"h1", "h2"}

    def test_framework_scores_combine_by_weight(self) -> None:
        scores = score_by_framework(
            [
                scored(ResultStatus.PASS, framework_id="f1"),
                scored(ResultStatus.FAIL, framework_id="f2"),
            ]
        )
        assert combine_framework_scores(scores) == 50.0
        assert combine_framework_scores(scores, {"f1": 3.0, "f2": 1.0}) == 75.0

    def test_an_unpublishable_framework_is_excluded_not_counted_as_zero(self) -> None:
        # A framework with too little data must not drag the overall
        # number down as though it had failed.
        scores = score_by_framework(
            [
                scored(ResultStatus.PASS, framework_id="f1"),
                scored(ResultStatus.PASS, framework_id="f2"),
            ],
            minimum_controls=1,
        )
        scores["f2"].publishable = False
        assert combine_framework_scores(scores) == 100.0

    def test_combining_nothing_publishable_is_zero(self) -> None:
        scores = score_by_framework([scored(ResultStatus.PASS, framework_id="f1")])
        scores["f1"].publishable = False
        assert combine_framework_scores(scores) == 0.0

    def test_combining_with_zero_total_weight_does_not_divide_by_zero(self) -> None:
        scores = score_by_framework([scored(ResultStatus.PASS, framework_id="f1")])
        assert combine_framework_scores(scores, {"f1": 0.0}) == 0.0

    @pytest.mark.parametrize(
        ("score", "grade"),
        [
            (100.0, ScoreGrade.EXCELLENT),
            (95.0, ScoreGrade.EXCELLENT),
            (94.9, ScoreGrade.GOOD),
            (85.0, ScoreGrade.GOOD),
            (70.0, ScoreGrade.FAIR),
            (50.0, ScoreGrade.POOR),
            (49.9, ScoreGrade.CRITICAL),
            (0.0, ScoreGrade.CRITICAL),
        ],
    )
    def test_grades_band_at_their_stated_boundaries(self, score: float, grade: ScoreGrade) -> None:
        assert grade_for(score) is grade

    def test_delta_needs_history(self) -> None:
        assert delta_of(90.0, None) is None
        assert delta_of(90.0, 85.0) == 5.0

    def test_a_trend_needs_two_points_and_a_deadband(self) -> None:
        # A dashboard that swings between "improving" and "declining" on
        # rounding teaches people to stop reading it.
        assert trend_of([]) == "insufficient_data"
        assert trend_of([("a", 80.0)]) == "insufficient_data"
        assert trend_of([("a", 80.0), ("b", 80.5)]) == "stable"
        assert trend_of([("a", 80.0), ("b", 90.0)]) == "improving"
        assert trend_of([("a", 90.0), ("b", 80.0)]) == "declining"


class TestRisk:
    @pytest.mark.parametrize(
        ("likelihood", "impact", "severity"),
        [
            (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.SEVERE, RiskSeverity.CRITICAL),
            (RiskLikelihood.LIKELY, RiskImpact.MAJOR, RiskSeverity.CRITICAL),
            (RiskLikelihood.POSSIBLE, RiskImpact.MODERATE, RiskSeverity.HIGH),
            (RiskLikelihood.UNLIKELY, RiskImpact.MODERATE, RiskSeverity.MODERATE),
            (RiskLikelihood.RARE, RiskImpact.NEGLIGIBLE, RiskSeverity.LOW),
        ],
    )
    def test_severity_is_derived_from_the_matrix(
        self, likelihood: RiskLikelihood, impact: RiskImpact, severity: RiskSeverity
    ) -> None:
        # Never entered. A register where somebody can type "low" beside
        # almost_certain/severe hides exactly the risks it exists to
        # surface, and the person most motivated to type it owns the risk.
        assert severity_for(likelihood, impact) is severity
        assert assess(likelihood, impact).severity is severity

    def test_the_worst_case_normalises_to_one_hundred(self) -> None:
        worst = assess(RiskLikelihood.ALMOST_CERTAIN, RiskImpact.SEVERE)
        assert worst.score == 25.0
        assert worst.normalised == 100.0

    def test_residual_risk_needs_both_halves(self) -> None:
        # Carrying the inherent likelihood forward would report a
        # mitigation as having reduced risk it never touched.
        assert residual(None, RiskImpact.MINOR) is None
        assert residual(RiskLikelihood.RARE, None) is None
        assert residual(RiskLikelihood.RARE, RiskImpact.MINOR) is not None

    def test_references_continue_from_the_highest_not_the_count(self) -> None:
        # Deleting an entry must not cause the next one to reuse a
        # reference already written down in somebody's meeting notes.
        assert next_reference([]) == "RISK-0001"
        assert next_reference(["RISK-0001", "RISK-0007"]) == "RISK-0008"
        assert next_reference(["RISK-0007"]) == "RISK-0008"
        assert next_reference(["not-a-reference"]) == "RISK-0001"

    def test_a_fingerprint_is_stable_for_the_same_problem_on_the_same_thing(self) -> None:
        first = fingerprint(control_id="c1", target_id="h1", target_type="server")
        second = fingerprint(control_id="c1", target_id="h1", target_type="server")
        assert first == second

    def test_a_fingerprint_separates_targets_and_controls(self) -> None:
        base = fingerprint(control_id="c1", target_id="h1")
        assert base != fingerprint(control_id="c1", target_id="h2")
        assert base != fingerprint(control_id="c2", target_id="h1")
        assert base != fingerprint(control_id="c1", target_id="h1", qualifier="port-22")

    def test_a_fingerprint_survives_a_changed_observation(self) -> None:
        # A host whose patch level moves from 4.1 to 4.2 while still
        # being out of date is the same unresolved problem. Re-raising it
        # would reset an age somebody is measured on.
        assert fingerprint(control_id="c1", target_id="h1") == fingerprint(
            control_id="c1", target_id="h1"
        )

    def test_severity_dominates_recurrence_in_the_urgency_score(self) -> None:
        # A medium seen 200 times outranks a medium seen once, but must
        # never outrank a critical -- "how often" is not "how bad", and a
        # queue sorted the other way sends people to the wrong fire.
        medium_often = risk_score_for_finding(FindingSeverity.MEDIUM, detection_count=200)
        medium_once = risk_score_for_finding(FindingSeverity.MEDIUM)
        critical_once = risk_score_for_finding(FindingSeverity.CRITICAL)
        assert medium_once < medium_often < critical_once

    def test_the_urgency_score_stays_below_one_hundred(self) -> None:
        assert risk_score_for_finding(FindingSeverity.CRITICAL, detection_count=10_000) < 100.0

    def test_due_dates_track_severity(self) -> None:
        assert due_at(FindingSeverity.CRITICAL, detected_at=NOW) == NOW + timedelta(days=7)
        assert due_at(FindingSeverity.LOW, detected_at=NOW) == NOW + timedelta(days=180)

    def test_an_informational_finding_gets_no_deadline(self) -> None:
        # An overdue queue full of things nobody is expected to act on is
        # how people learn to ignore the ones that matter.
        assert due_at(FindingSeverity.INFORMATIONAL, detected_at=NOW) is None

    def test_overdue_needs_a_due_date(self) -> None:
        assert is_overdue(None) is False
        assert is_overdue(NOW - timedelta(days=1), now=NOW) is True
        assert is_overdue(NOW + timedelta(days=1), now=NOW) is False

    def test_review_is_measured_from_the_last_review_or_from_creation(self) -> None:
        # A risk registered a year ago and never looked at is
        # immediately overdue, rather than being given a fresh window by
        # the act of asking.
        created = NOW - timedelta(days=400)
        assert next_review(last_reviewed=None, interval_days=90, created_at=created) < NOW
        assert next_review(last_reviewed=NOW, interval_days=90, created_at=created) > NOW


class TestBuiltinCatalogue:
    def test_every_shipped_control_has_a_valid_rule(self) -> None:
        # A shipped catalogue whose controls do not evaluate would look
        # impressive and assess nothing, and an organization would find
        # that out only after wiring up their estate.
        for framework in BUILTIN_FRAMEWORKS:
            for one in framework.controls:
                validate_rule(one.rule)

    def test_every_shipped_control_actually_decides_something(self) -> None:
        # Each rule is exercised against a payload that should fail it,
        # so a rule that passes unconditionally cannot slip through.
        for framework in BUILTIN_FRAMEWORKS:
            for one in framework.controls:
                empty = evaluate_control(
                    EvaluableControl(
                        control_id=one.code,
                        framework_id=framework.slug,
                        code=one.code,
                        title=one.title,
                        severity=one.severity,
                        status=ControlStatus.IMPLEMENTED,
                        is_automatable=True,
                        rule=one.rule,
                    ),
                    Target("h1", "server", payload={"unrelated": True}),
                    now=NOW,
                )
                where = f"{framework.slug}/{one.code}"
                assert empty.status is ResultStatus.FAIL, where

    def test_every_shipped_control_has_remediation_guidance(self) -> None:
        # A failure an operator cannot act on is a failure nobody fixes.
        for framework in BUILTIN_FRAMEWORKS:
            for one in framework.controls:
                assert one.remediation_guidance, f"{framework.slug}/{one.code}"

    def test_control_codes_are_unique_within_a_framework(self) -> None:
        for framework in BUILTIN_FRAMEWORKS:
            codes = [one.code for one in framework.controls]
            assert len(codes) == len(set(codes)), framework.slug

    def test_framework_slugs_are_unique(self) -> None:
        slugs = [one.slug for one in BUILTIN_FRAMEWORKS]
        assert len(slugs) == len(set(slugs))

    def test_every_mapping_names_controls_that_exist(self) -> None:
        # A mapping to a control that is not there silently drops a
        # framework's coverage without saying so.
        for mapping in BUILTIN_MAPPINGS:
            source = framework_by_slug(mapping.source_framework)
            target = framework_by_slug(mapping.target_framework)
            assert source is not None, mapping.source_framework
            assert target is not None, mapping.target_framework
            assert any(one.code == mapping.source_code for one in source.controls), mapping
            assert any(one.code == mapping.target_code for one in target.controls), mapping

    def test_an_inferred_mapping_is_not_asserted_at_full_confidence(self) -> None:
        # A report that treats an inferred equivalence like a published
        # one is overstating its coverage.
        inferred = [one for one in BUILTIN_MAPPINGS if one.relation.value == "supports"]
        assert inferred, "the catalogue should contain at least one inferred mapping"
        assert all(one.confidence < 1.0 for one in inferred)

    def test_the_catalogue_publishes_the_paths_a_collector_must_produce(self) -> None:
        paths = all_evidence_paths()
        assert "firewall.enabled" in paths
        assert paths == sorted(set(paths))

    def test_an_unknown_slug_is_none_not_an_error(self) -> None:
        assert framework_by_slug("not-a-framework") is None
