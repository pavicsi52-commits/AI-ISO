"""Tallying a CAB review's votes.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

from app.cab.engine import quorum_met, tally
from app.models.enums import CabVote


class TestQuorumMet:
    def test_zero_invited_never_meets_quorum(self) -> None:
        assert quorum_met(votes_cast=0, invited_count=0, quorum_fraction=0.5) is False

    def test_half_of_invited_meets_a_half_quorum(self) -> None:
        assert quorum_met(votes_cast=3, invited_count=6, quorum_fraction=0.5) is True

    def test_below_the_fraction_does_not_meet_quorum(self) -> None:
        assert quorum_met(votes_cast=2, invited_count=6, quorum_fraction=0.5) is False

    def test_everyone_voting_always_meets_quorum(self) -> None:
        assert quorum_met(votes_cast=6, invited_count=6, quorum_fraction=0.99) is True


class TestTally:
    def test_quorum_not_met_produces_no_outcome(self) -> None:
        result = tally([CabVote.APPROVE], invited_count=10, quorum_fraction=0.5)
        assert result.quorum_met is False
        assert result.outcome is None

    def test_all_approve_is_approved(self) -> None:
        votes = [CabVote.APPROVE, CabVote.APPROVE, CabVote.APPROVE]
        result = tally(votes, invited_count=3, quorum_fraction=0.5)
        assert result.quorum_met is True
        assert result.outcome is CabVote.APPROVE

    def test_a_single_rejection_sinks_the_change_regardless_of_other_votes(self) -> None:
        votes = [CabVote.APPROVE, CabVote.APPROVE, CabVote.REJECT]
        result = tally(votes, invited_count=3, quorum_fraction=0.5)
        assert result.outcome is CabVote.REJECT

    def test_a_conditional_vote_makes_the_outcome_conditional_absent_a_rejection(self) -> None:
        votes = [CabVote.APPROVE, CabVote.CONDITIONAL]
        result = tally(votes, invited_count=2, quorum_fraction=0.5)
        assert result.outcome is CabVote.CONDITIONAL

    def test_rejection_outranks_conditional(self) -> None:
        votes = [CabVote.CONDITIONAL, CabVote.REJECT]
        result = tally(votes, invited_count=2, quorum_fraction=0.5)
        assert result.outcome is CabVote.REJECT

    def test_all_abstain_with_quorum_met_produces_no_outcome(self) -> None:
        votes = [CabVote.ABSTAIN, CabVote.ABSTAIN]
        result = tally(votes, invited_count=2, quorum_fraction=0.5)
        assert result.quorum_met is True
        assert result.outcome is None

    def test_counts_are_reported_regardless_of_quorum(self) -> None:
        votes = [CabVote.APPROVE, CabVote.REJECT, CabVote.CONDITIONAL, CabVote.ABSTAIN]
        result = tally(votes, invited_count=100, quorum_fraction=0.9)
        assert result.quorum_met is False
        assert result.approve_count == 1
        assert result.reject_count == 1
        assert result.conditional_count == 1
        assert result.abstain_count == 1
