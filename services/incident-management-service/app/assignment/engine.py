"""Choosing who an incident goes to.

Pure: takes a roster and a request, returns a choice. Nothing here reads
an on-call schedule or a database -- ``app/services/assignment.py``
resolves the current roster and hands it in, which is what makes "why
did this incident go to Alice and not Bob" a question this module can
answer from its arguments alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import AssignmentMethod


@dataclass(frozen=True, slots=True)
class Responder:
    """One person or team who could take an incident."""

    responder_id: str
    team: str | None = None
    skills: frozenset[str] = field(default_factory=frozenset)
    open_incident_count: int = 0
    is_on_call: bool = False
    is_available: bool = True


@dataclass(frozen=True, slots=True)
class AssignmentDecision:
    """Who was chosen, how, and why -- the "why" is what a worklog needs."""

    responder: Responder
    method: AssignmentMethod
    reason: str


def eligible(
    roster: list[Responder],
    *,
    required_skills: frozenset[str] = frozenset(),
    on_call_only: bool = False,
) -> list[Responder]:
    """The subset of a roster that could actually take this incident.

    Unavailable responders are excluded unconditionally -- a responder
    marked unavailable is unavailable regardless of how well their
    skills match, and assigning to them anyway is how an incident ends
    up assigned to someone who is on leave.
    """
    return [
        one
        for one in roster
        if one.is_available
        and (not on_call_only or one.is_on_call)
        and required_skills <= one.skills
    ]


def assign_by_load(roster: list[Responder]) -> AssignmentDecision | None:
    """The eligible responder carrying the least open work.

    Ties broken by ``responder_id`` so the choice is deterministic --
    two responders at the same load must resolve to the same answer
    every time this runs, or "why did it pick Bob and not Alice, they
    were tied" has no defensible answer.
    """
    if not roster:
        return None
    chosen = min(roster, key=lambda one: (one.open_incident_count, one.responder_id))
    return AssignmentDecision(
        responder=chosen,
        method=AssignmentMethod.LOAD_BALANCED,
        reason=(
            f"Lowest open-incident count among eligible responders ({chosen.open_incident_count})."
        ),
    )


def assign_by_skill(
    roster: list[Responder], *, required_skills: frozenset[str]
) -> AssignmentDecision | None:
    """The lowest-loaded responder who actually has the needed skills.

    Skill match narrows the pool first; load only breaks ties within it.
    Assigning a database incident to the least-loaded responder without
    regard for whether they know the database is how an incident sits
    unworked while looking assigned.
    """
    matching = eligible(roster, required_skills=required_skills)
    if not matching:
        return None
    decision = assign_by_load(matching)
    if decision is None:
        return None
    return AssignmentDecision(
        responder=decision.responder,
        method=AssignmentMethod.SKILL_BASED,
        reason=f"Matched skills {sorted(required_skills)} among eligible responders; "
        f"lowest load ({decision.responder.open_incident_count}) broke the tie.",
    )


def assign_on_call(roster: list[Responder]) -> AssignmentDecision | None:
    """The lowest-loaded responder currently on call."""
    on_call = eligible(roster, on_call_only=True)
    if not on_call:
        return None
    decision = assign_by_load(on_call)
    if decision is None:
        return None
    return AssignmentDecision(
        responder=decision.responder,
        method=AssignmentMethod.ON_CALL,
        reason="On-call rotation; lowest load broke a tie among on-call responders.",
    )


def assign(
    roster: list[Responder],
    *,
    required_skills: frozenset[str] = frozenset(),
    prefer_on_call: bool = True,
) -> AssignmentDecision | None:
    """The platform's default assignment policy, in order of preference.

    On-call and skill-matched are tried before a plain load-balanced
    fallback, and **on-call is tried first** when both are requested:
    an on-call responder who happens to lack the exact skill tag is
    still the person whose job is to be reachable right now, which
    matters more at the moment of assignment than a skill match that
    can be corrected by reassignment once someone is actually looking.
    """
    if prefer_on_call:
        decision = assign_on_call(roster)
        if decision is not None:
            return decision
    if required_skills:
        decision = assign_by_skill(roster, required_skills=required_skills)
        if decision is not None:
            return decision
    return assign_by_load(eligible(roster))


__all__ = [
    "AssignmentDecision",
    "Responder",
    "assign",
    "assign_by_load",
    "assign_by_skill",
    "assign_on_call",
    "eligible",
]
