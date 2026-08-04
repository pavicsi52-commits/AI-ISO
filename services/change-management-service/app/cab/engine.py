"""Tallying a Change Advisory Board's votes into one outcome.

Pure -- takes the votes cast, the quorum policy, and how many members
were invited, returns whether quorum was met and what the board decided.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import CabVote


@dataclass(frozen=True, slots=True)
class CabTally:
    """The result of counting one CAB review's votes."""

    quorum_met: bool
    outcome: CabVote | None
    """``None`` when quorum was not met -- a board that never actually
    convened has not decided anything, and reporting an outcome anyway
    would misrepresent a quorum failure as a real vote."""

    approve_count: int
    reject_count: int
    conditional_count: int
    abstain_count: int


def quorum_met(*, votes_cast: int, invited_count: int, quorum_fraction: float) -> bool:
    """Whether enough invited members actually voted.

    An invited count of zero can never meet quorum, regardless of the
    fraction required -- a board with nobody invited is not a quorum
    edge case, it is a meeting that was never properly convened.
    """
    if invited_count <= 0:
        return False
    return (votes_cast / invited_count) >= quorum_fraction


def tally(votes: list[CabVote], *, invited_count: int, quorum_fraction: float) -> CabTally:
    """Tally a review's votes into one outcome.

    **A single rejection sinks the change.** Unlike a simple majority,
    one board member's rejection is enough to fail the review -- CAB
    exists to catch a real objection, and a vote-counting rule that lets
    a rejection be outvoted defeats that purpose. Failing that, any
    conditional vote makes the outcome conditional, and the change
    proceeds only once whatever the board attached is satisfied. Only
    when every vote is a clean approval does the outcome become
    ``APPROVE``; abstentions count toward quorum but decide nothing.
    """
    met = quorum_met(
        votes_cast=len(votes), invited_count=invited_count, quorum_fraction=quorum_fraction
    )
    counts = CabTally(
        quorum_met=met,
        outcome=None,
        approve_count=sum(1 for one in votes if one is CabVote.APPROVE),
        reject_count=sum(1 for one in votes if one is CabVote.REJECT),
        conditional_count=sum(1 for one in votes if one is CabVote.CONDITIONAL),
        abstain_count=sum(1 for one in votes if one is CabVote.ABSTAIN),
    )
    if not met:
        return counts

    if counts.reject_count > 0:
        outcome = CabVote.REJECT
    elif counts.conditional_count > 0:
        outcome = CabVote.CONDITIONAL
    elif counts.approve_count > 0:
        outcome = CabVote.APPROVE
    else:
        # Every cast vote was an abstention: quorum was technically met,
        # but nobody actually took a position. Treated as no decision,
        # not as a silent approval.
        outcome = None

    return CabTally(
        quorum_met=met,
        outcome=outcome,
        approve_count=counts.approve_count,
        reject_count=counts.reject_count,
        conditional_count=counts.conditional_count,
        abstain_count=counts.abstain_count,
    )


__all__ = ["CabTally", "quorum_met", "tally"]
