"""Rolling individual service/asset impacts into one overall assessment.

Pure: takes the impacts recorded so far, returns a summary. Nothing here
walks a knowledge graph -- ``app/services/impact.py`` does that and
hands the resulting service/asset list in, which keeps the "how do we
summarise impact" question testable independently of "how do we
discover what is affected."
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import IMPACT_ORDER, ImpactLevel, RiskLevel

HIGH_RISK_SERVICE_COUNT = 10
"""Enough affected services to rank as high risk on breadth alone,
independent of how severe any single reading is."""

MODERATE_RISK_SERVICE_COUNT = 3


@dataclass(frozen=True, slots=True)
class ServiceImpact:
    """One affected service, as the summariser needs it."""

    service_name: str
    impact_level: ImpactLevel
    is_root: bool = False


def overall_impact(impacts: list[ServiceImpact]) -> ImpactLevel:
    """The worst impact among everything affected.

    Worst, not average or root-only. An incident with nineteen services
    at MINOR and one at SEVERE is a severe incident -- averaging would
    launder the one thing that actually matters, and reporting only the
    root service's impact would miss a genuinely severe knock-on effect
    on something the root service does not itself depend on being fine.
    """
    if not impacts:
        return ImpactLevel.NONE
    return max((one.impact_level for one in impacts), key=lambda level: IMPACT_ORDER[level])


def risk_level_for(
    *, overall: ImpactLevel, affected_service_count: int, has_customer_impact: bool
) -> RiskLevel:
    """A coarse risk banding from impact severity and breadth.

    Breadth matters independently of severity: twelve services each
    minorly affected is a different risk profile than one service
    minorly affected, even though no single impact reading is high, and
    a banding that only looked at the worst individual impact would
    treat them identically.
    """
    order = IMPACT_ORDER[overall]
    if order >= IMPACT_ORDER[ImpactLevel.SEVERE] or (
        has_customer_impact and order >= IMPACT_ORDER[ImpactLevel.MAJOR]
    ):
        return RiskLevel.CRITICAL
    if (
        order >= IMPACT_ORDER[ImpactLevel.MAJOR]
        or affected_service_count >= HIGH_RISK_SERVICE_COUNT
    ):
        return RiskLevel.HIGH
    if (
        order >= IMPACT_ORDER[ImpactLevel.MODERATE]
        or affected_service_count >= MODERATE_RISK_SERVICE_COUNT
    ):
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def root_services(impacts: list[ServiceImpact]) -> list[ServiceImpact]:
    """The services flagged as where the problem originated.

    What separates "here is everything affected" from "here is where to
    go fix it" -- a distinction that matters most exactly when the
    affected list is long enough that nobody can read all of it during
    an active incident.
    """
    return [one for one in impacts if one.is_root]


def summarise(impacts: list[ServiceImpact]) -> dict[str, int]:
    """How many affected services fall in each impact band."""
    tally: dict[str, int] = {str(one): 0 for one in ImpactLevel}
    for one in impacts:
        tally[str(one.impact_level)] += 1
    return tally


__all__ = ["ServiceImpact", "overall_impact", "risk_level_for", "root_services", "summarise"]
