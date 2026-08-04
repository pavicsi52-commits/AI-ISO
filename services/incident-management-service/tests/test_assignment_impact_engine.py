"""Assignment selection and impact summarisation."""

from __future__ import annotations

from app.assignment.engine import (
    Responder,
    assign,
    assign_by_load,
    assign_by_skill,
    assign_on_call,
    eligible,
)
from app.impact.engine import (
    ServiceImpact,
    overall_impact,
    risk_level_for,
    root_services,
    summarise,
)
from app.models.enums import AssignmentMethod, ImpactLevel, RiskLevel


def responder(
    responder_id: str,
    *,
    skills: frozenset[str] = frozenset(),
    load: int = 0,
    on_call: bool = False,
    available: bool = True,
) -> Responder:
    return Responder(
        responder_id=responder_id,
        skills=skills,
        open_incident_count=load,
        is_on_call=on_call,
        is_available=available,
    )


class TestEligible:
    def test_unavailable_is_excluded_regardless_of_fit(self) -> None:
        roster = [responder("a", on_call=True, available=False)]
        assert eligible(roster, on_call_only=True) == []

    def test_skills_are_a_subset_requirement(self) -> None:
        roster = [
            responder("a", skills=frozenset({"database"})),
            responder("b", skills=frozenset({"database", "network"})),
        ]
        found = eligible(roster, required_skills=frozenset({"database", "network"}))
        assert [one.responder_id for one in found] == ["b"]

    def test_no_requirements_admits_everyone_available(self) -> None:
        roster = [responder("a"), responder("b", available=False)]
        assert [one.responder_id for one in eligible(roster)] == ["a"]


class TestAssignByLoad:
    def test_the_least_loaded_responder_is_chosen(self) -> None:
        roster = [responder("a", load=5), responder("b", load=1)]
        decision = assign_by_load(roster)
        assert decision is not None
        assert decision.responder.responder_id == "b"
        assert decision.method is AssignmentMethod.LOAD_BALANCED

    def test_ties_break_deterministically_by_id(self) -> None:
        roster = [responder("charlie", load=2), responder("alice", load=2)]
        decision = assign_by_load(roster)
        assert decision is not None
        assert decision.responder.responder_id == "alice"

    def test_an_empty_roster_yields_no_decision(self) -> None:
        assert assign_by_load([]) is None


class TestAssignBySkill:
    def test_skill_match_narrows_before_load_breaks_the_tie(self) -> None:
        roster = [
            responder("generalist", load=0),
            responder("specialist", skills=frozenset({"database"}), load=3),
        ]
        decision = assign_by_skill(roster, required_skills=frozenset({"database"}))
        assert decision is not None
        assert decision.responder.responder_id == "specialist"
        assert decision.method is AssignmentMethod.SKILL_BASED

    def test_no_skill_match_yields_no_decision(self) -> None:
        roster = [responder("a", skills=frozenset({"network"}))]
        assert assign_by_skill(roster, required_skills=frozenset({"database"})) is None


class TestAssignOnCall:
    def test_only_on_call_responders_are_considered(self) -> None:
        roster = [responder("off-call", load=0), responder("on-call", load=5, on_call=True)]
        decision = assign_on_call(roster)
        assert decision is not None
        assert decision.responder.responder_id == "on-call"
        assert decision.method is AssignmentMethod.ON_CALL

    def test_nobody_on_call_yields_no_decision(self) -> None:
        assert assign_on_call([responder("a")]) is None


class TestAssignPolicy:
    def test_on_call_is_preferred_over_a_skill_match(self) -> None:
        # An on-call responder without the exact skill tag is still the
        # person whose job is to be reachable right now.
        roster = [
            responder("specialist", skills=frozenset({"database"})),
            responder("on-call", on_call=True),
        ]
        decision = assign(roster, required_skills=frozenset({"database"}))
        assert decision is not None
        assert decision.responder.responder_id == "on-call"

    def test_falls_back_to_skill_when_nobody_is_on_call(self) -> None:
        roster = [responder("specialist", skills=frozenset({"database"}))]
        decision = assign(roster, required_skills=frozenset({"database"}))
        assert decision is not None
        assert decision.method is AssignmentMethod.SKILL_BASED

    def test_falls_back_to_load_when_nothing_else_applies(self) -> None:
        roster = [responder("a", load=3), responder("b", load=1)]
        decision = assign(roster)
        assert decision is not None
        assert decision.responder.responder_id == "b"
        assert decision.method is AssignmentMethod.LOAD_BALANCED

    def test_on_call_preference_can_be_disabled(self) -> None:
        roster = [
            responder("specialist", skills=frozenset({"database"})),
            responder("on-call", on_call=True),
        ]
        decision = assign(roster, required_skills=frozenset({"database"}), prefer_on_call=False)
        assert decision is not None
        assert decision.responder.responder_id == "specialist"

    def test_an_empty_roster_yields_no_decision(self) -> None:
        assert assign([]) is None


class TestOverallImpact:
    def test_worst_impact_wins_not_average(self) -> None:
        impacts = [
            ServiceImpact("a", ImpactLevel.MINOR),
            ServiceImpact("b", ImpactLevel.SEVERE),
        ]
        assert overall_impact(impacts) is ImpactLevel.SEVERE

    def test_no_impacts_is_none(self) -> None:
        assert overall_impact([]) is ImpactLevel.NONE


class TestRiskLevel:
    def test_severe_impact_is_critical_risk(self) -> None:
        assert (
            risk_level_for(
                overall=ImpactLevel.SEVERE, affected_service_count=1, has_customer_impact=False
            )
            is RiskLevel.CRITICAL
        )

    def test_major_impact_with_customer_impact_is_critical(self) -> None:
        # Breadth-independent escalation: customer-facing major impact
        # is treated as critical even with only one service affected.
        assert (
            risk_level_for(
                overall=ImpactLevel.MAJOR, affected_service_count=1, has_customer_impact=True
            )
            is RiskLevel.CRITICAL
        )

    def test_wide_but_shallow_impact_is_still_elevated(self) -> None:
        # Twelve minorly-affected services is a different risk profile
        # than one, even though no single reading is high.
        assert (
            risk_level_for(
                overall=ImpactLevel.MINOR, affected_service_count=12, has_customer_impact=False
            )
            is RiskLevel.HIGH
        )

    def test_a_single_minor_impact_is_low_risk(self) -> None:
        assert (
            risk_level_for(
                overall=ImpactLevel.MINOR, affected_service_count=1, has_customer_impact=False
            )
            is RiskLevel.LOW
        )

    def test_moderate_impact_is_moderate_risk(self) -> None:
        assert (
            risk_level_for(
                overall=ImpactLevel.MODERATE, affected_service_count=1, has_customer_impact=False
            )
            is RiskLevel.MODERATE
        )


class TestRootServices:
    def test_only_root_flagged_services_are_returned(self) -> None:
        impacts = [
            ServiceImpact("origin", ImpactLevel.SEVERE, is_root=True),
            ServiceImpact("downstream", ImpactLevel.MODERATE, is_root=False),
        ]
        assert [one.service_name for one in root_services(impacts)] == ["origin"]

    def test_no_root_flagged_services_is_empty(self) -> None:
        assert root_services([ServiceImpact("a", ImpactLevel.MINOR)]) == []


class TestSummarise:
    def test_every_band_is_present_even_at_zero(self) -> None:
        tally = summarise([])
        assert set(tally) == {str(one) for one in ImpactLevel}
        assert all(value == 0 for value in tally.values())

    def test_counts_land_in_the_right_band(self) -> None:
        impacts = [
            ServiceImpact("a", ImpactLevel.MINOR),
            ServiceImpact("b", ImpactLevel.MINOR),
            ServiceImpact("c", ImpactLevel.SEVERE),
        ]
        tally = summarise(impacts)
        assert tally[str(ImpactLevel.MINOR)] == 2
        assert tally[str(ImpactLevel.SEVERE)] == 1
