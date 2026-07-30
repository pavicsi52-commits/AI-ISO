"""Quota arithmetic: periods, headroom, and what to do at the limit.

Pure functions over quota rows. The database side -- incrementing
consumption atomically -- lives in the repository, because that is the
part that must not be a read-modify-write in Python.

**A quota that only speaks when it is exhausted is useless.** By the
time consumption hits the limit, work is already failing; the warning
threshold exists so an operator hears about it while there is still
something to do.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import PolicyEffect, QuotaPeriod

_PERIOD_LENGTHS: dict[QuotaPeriod, timedelta | None] = {
    QuotaPeriod.HOURLY: timedelta(hours=1),
    QuotaPeriod.DAILY: timedelta(days=1),
    QuotaPeriod.WEEKLY: timedelta(weeks=1),
    QuotaPeriod.MONTHLY: None,
    QuotaPeriod.TOTAL: None,
}
"""How long each period runs.

``MONTHLY`` is ``None`` because a month is not a fixed span -- adding 30
days to 31 January lands in March and skips a whole billing period.
``TOTAL`` is ``None`` because it never resets at all.
"""


@dataclass(frozen=True, slots=True)
class QuotaState:
    """A quota's current standing, as a decision needs to see it."""

    scope: str
    resource: str
    limit_value: float
    consumed: float
    period: QuotaPeriod
    is_hard_limit: bool
    period_started_at: datetime

    @property
    def unlimited(self) -> bool:
        """Whether this quota imposes no ceiling.

        A limit of zero means *unlimited*, not "nothing allowed". That
        reading is chosen deliberately and stated loudly: a quota row
        created without a limit -- by a migration default, a partial
        form, a bad import -- would otherwise refuse every request for
        that resource, and an accidental total outage is a far worse
        failure than an accidental absence of enforcement. A genuine
        "nothing allowed" is expressible as an ordinary DENY policy,
        which is where a refusal belongs.
        """
        return self.limit_value <= 0

    @property
    def remaining(self) -> float:
        """Headroom left in this period."""
        if self.unlimited:
            return float("inf")
        return max(0.0, self.limit_value - self.consumed)

    @property
    def usage_ratio(self) -> float:
        """Fraction of the limit consumed, 0.0-1.0+."""
        if self.unlimited:
            return 0.0
        return self.consumed / self.limit_value

    @property
    def exceeded(self) -> bool:
        """Whether consumption has reached the limit."""
        return not self.unlimited and self.consumed >= self.limit_value

    def would_exceed(self, amount: float) -> bool:
        """Whether consuming *amount* more would pass the limit."""
        return not self.unlimited and (self.consumed + amount) > self.limit_value

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "scope": self.scope,
            "resource": self.resource,
            "limit": self.limit_value,
            "consumed": self.consumed,
            "remaining": None if self.unlimited else self.remaining,
            "usage_ratio": round(self.usage_ratio, 4),
            "unlimited": self.unlimited,
            "exceeded": self.exceeded,
            "period": str(self.period),
            "period_started_at": self.period_started_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class QuotaCheck:
    """The outcome of checking one request against the quotas."""

    permitted: bool
    effect: PolicyEffect
    reason: str
    states: list[QuotaState]
    warnings: list[str]
    blocking: QuotaState | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "permitted": self.permitted,
            "effect": str(self.effect),
            "reason": self.reason,
            "warnings": self.warnings,
            "quotas": [one.as_dict() for one in self.states],
            "blocking": self.blocking.as_dict() if self.blocking is not None else None,
        }


def period_start(moment: datetime, period: QuotaPeriod) -> datetime:
    """The start of the period *moment* falls in.

    Computed by truncation rather than by subtracting a span, so a daily
    quota resets at midnight rather than 24 hours after whenever it was
    created -- which is what an operator means by "daily" and what makes
    two quotas created hours apart reset together.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    if period is QuotaPeriod.HOURLY:
        return aware.replace(minute=0, second=0, microsecond=0)
    if period is QuotaPeriod.DAILY:
        return aware.replace(hour=0, minute=0, second=0, microsecond=0)
    if period is QuotaPeriod.WEEKLY:
        midnight = aware.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=midnight.weekday())
    if period is QuotaPeriod.MONTHLY:
        return aware.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # TOTAL never resets, so its period began whenever the quota did.
    return aware


def period_end(start: datetime, period: QuotaPeriod) -> datetime | None:
    """When a period that began at *start* ends, or ``None`` if never."""
    if period is QuotaPeriod.TOTAL:
        return None
    if period is QuotaPeriod.MONTHLY:
        # Calendar-aware: adding 30 days to 31 January lands in March and
        # skips February entirely.
        days = monthrange(start.year, start.month)[1]
        return start + timedelta(days=days)
    span = _PERIOD_LENGTHS[period]
    return start + span if span is not None else None


def needs_reset(state: QuotaState, *, now: datetime) -> bool:
    """Whether a quota's period has rolled over since it was last touched."""
    if state.period is QuotaPeriod.TOTAL:
        return False
    return period_start(now, state.period) > state.period_started_at


def check(
    states: list[QuotaState],
    *,
    amount: float = 1.0,
    warning_threshold: float = 0.8,
    enforcement_enabled: bool = True,
) -> QuotaCheck:
    """Decide whether a request fits inside every quota that applies.

    **Every quota is checked, not just the first that blocks.** A caller
    told only about the first exhausted budget will raise it, retry, and
    hit the next one -- so the check reports all of them, and names the
    tightest as the blocker.
    """
    warnings: list[str] = []
    blockers: list[QuotaState] = []

    for state in states:
        if state.unlimited:
            continue
        if state.would_exceed(amount):
            blockers.append(state)
        elif (state.consumed + amount) / state.limit_value >= warning_threshold:
            warnings.append(
                f"{state.resource!r} is at "
                f"{round(((state.consumed + amount) / state.limit_value) * 100)}% "
                f"of its {state.period!s} quota for {state.scope!r}."
            )

    if not blockers:
        return QuotaCheck(
            permitted=True,
            effect=PolicyEffect.ALLOW,
            reason="Every applicable quota has headroom.",
            states=states,
            warnings=warnings,
        )

    hard = [one for one in blockers if one.is_hard_limit]
    if not enforcement_enabled or not hard:
        # A soft limit is how a quota gets introduced without breaking
        # the people already over it. It warns and lets the request
        # through, which is the whole reason for having the distinction.
        for one in blockers:
            warnings.append(
                f"{one.resource!r} is over its {one.period!s} quota for "
                f"{one.scope!r} ({one.consumed:g}/{one.limit_value:g}), but the limit "
                f"is {'not enforced' if not enforcement_enabled else 'soft'}."
            )
        return QuotaCheck(
            permitted=True,
            effect=PolicyEffect.ALLOW,
            reason="Over quota, but no hard limit applies.",
            states=states,
            warnings=warnings,
        )

    tightest = min(hard, key=lambda one: one.remaining)
    others = len(hard) - 1
    reason = (
        f"{tightest.resource!r} is at its {tightest.period!s} quota for "
        f"{tightest.scope!r}: {tightest.consumed:g} of {tightest.limit_value:g} used, "
        f"{amount:g} more requested."
    )
    if others:
        reason += f" {others} other quota{'s' if others > 1 else ''} also blocked."
    return QuotaCheck(
        permitted=False,
        effect=PolicyEffect.QUOTA_EXCEEDED,
        reason=reason,
        states=states,
        warnings=warnings,
        blocking=tightest,
    )


def state_from_row(row: Any) -> QuotaState:
    """Build a :class:`QuotaState` from a stored quota row."""
    return QuotaState(
        scope=f"{row.scope}:{row.scope_id}" if row.scope_id else str(row.scope),
        resource=row.resource,
        limit_value=float(row.limit_value or 0.0),
        consumed=float(row.consumed or 0.0),
        period=QuotaPeriod(str(row.period)),
        is_hard_limit=bool(row.is_hard_limit),
        period_started_at=row.period_started_at,
    )


__all__ = [
    "QuotaCheck",
    "QuotaState",
    "check",
    "needs_reset",
    "period_end",
    "period_start",
    "state_from_row",
]
