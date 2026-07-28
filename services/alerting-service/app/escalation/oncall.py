"""On-call resolution ("ON-CALL MANAGEMENT" "Support": Schedules,
Rotations, Time Zones, Overrides, Holiday Calendars).

Resolves which participant is on call for a schedule at a given
moment. Pure computation over an already-fetched
:class:`~app.models.alert_oncall_schedule.AlertOnCallSchedule` row.

Order of precedence, most specific first:

1. An **override** covering the moment always wins ("Overrides" exists
   precisely to beat the computed rotation).
2. A date listed in ``holiday_calendar`` has **no one** on call --
   returning ``None`` rather than silently paging whoever the rotation
   would have picked, so the caller escalates instead of quietly
   notifying someone who is off.
3. Otherwise the rotation slot is computed from elapsed periods since
   the schedule's own creation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.alert_oncall_schedule import AlertOnCallSchedule
from app.models.enums import OnCallRotationType

_ROTATION_PERIOD: dict[OnCallRotationType, timedelta] = {
    OnCallRotationType.DAILY: timedelta(days=1),
    OnCallRotationType.WEEKLY: timedelta(weeks=1),
    OnCallRotationType.BIWEEKLY: timedelta(weeks=2),
    OnCallRotationType.CUSTOM: timedelta(weeks=1),
}
"""``CUSTOM`` falls back to weekly -- no per-schedule custom period
column exists in docs/045's own 16-table schema, so ``CUSTOM`` is
honoured as "an operator-labelled rotation" rather than inventing a
cadence field the schema never asked for.
"""


def _parse_moment(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _active_override(schedule: AlertOnCallSchedule, moment: datetime) -> str | None:
    for override in schedule.overrides:
        if not isinstance(override, dict):
            continue
        user_id = override.get("user_id")
        starts_at = _parse_moment(override.get("starts_at"))
        ends_at = _parse_moment(override.get("ends_at"))
        if not user_id or starts_at is None or ends_at is None:
            continue
        if starts_at <= moment <= ends_at:
            return str(user_id)
    return None


def _is_holiday(schedule: AlertOnCallSchedule, moment: datetime) -> bool:
    return moment.date().isoformat() in set(schedule.holiday_calendar)


def resolve_oncall(schedule: AlertOnCallSchedule, moment: datetime) -> str | None:
    """Return the user id on call at *moment*, or ``None`` if nobody is."""
    if not schedule.enabled:
        return None
    override = _active_override(schedule, moment)
    if override is not None:
        return override
    if _is_holiday(schedule, moment):
        return None
    if not schedule.participants:
        return None
    period = _ROTATION_PERIOD[
        (
            schedule.rotation_type
            if isinstance(schedule.rotation_type, OnCallRotationType)
            else OnCallRotationType(schedule.rotation_type)
        )
    ]
    elapsed = moment - schedule.created_at
    if elapsed < timedelta(0):
        return str(schedule.participants[0])
    slot = int(elapsed // period) % len(schedule.participants)
    return str(schedule.participants[slot])


__all__ = ["resolve_oncall"]
