"""Calendar schedules and business hours.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "SCHEDULING TYPES":
Calendar Schedule, Business Hours. Parses
:attr:`shared_core.scheduler.schedule.Schedule.calendar_rule`'s simple
text format (``"MON-FRI 09:00-17:00"`` or ``"MON,WED,FRI 09:00-17:00"``)
into a checkable rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from shared_core.scheduler.exceptions import InvalidScheduleError
from shared_core.scheduler.timezone import localize

_CALENDAR_RULE_TOKEN_COUNT = 2

_WEEKDAY_NAMES: dict[str, int] = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}
_WEEKDAY_ORDER = list(_WEEKDAY_NAMES)


@dataclass(frozen=True, slots=True)
class CalendarRule:
    """A recurring weekly window: which weekdays, and what time-of-day range on each."""

    weekdays: frozenset[int]
    start_time: time
    end_time: time

    def is_active(self, moment: datetime, *, timezone_name: str = "UTC") -> bool:
        """Whether *moment* falls within this rule's active window.

        A naive *moment* is interpreted as already being in
        *timezone_name*; an aware one is converted to it first.
        """
        local = moment if moment.tzinfo is not None else localize(moment, timezone_name)
        if local.weekday() not in self.weekdays:
            return False
        local_time = local.timetz().replace(tzinfo=None)
        if self.start_time <= self.end_time:
            return self.start_time <= local_time < self.end_time
        return local_time >= self.start_time or local_time < self.end_time


def _parse_weekdays(token: str) -> frozenset[int]:
    if "-" in token:
        start_name, _dash, end_name = token.partition("-")
        start_name, end_name = start_name.strip().upper(), end_name.strip().upper()
        if start_name not in _WEEKDAY_NAMES or end_name not in _WEEKDAY_NAMES:
            raise InvalidScheduleError(f"Invalid weekday range {token!r}.")
        start_index, end_index = _WEEKDAY_ORDER.index(start_name), _WEEKDAY_ORDER.index(end_name)
        if start_index <= end_index:
            names = _WEEKDAY_ORDER[start_index : end_index + 1]
        else:
            names = _WEEKDAY_ORDER[start_index:] + _WEEKDAY_ORDER[: end_index + 1]
        return frozenset(_WEEKDAY_NAMES[name] for name in names)

    names = [part.strip().upper() for part in token.split(",") if part.strip()]
    if not names or any(name not in _WEEKDAY_NAMES for name in names):
        raise InvalidScheduleError(f"Invalid weekday list {token!r}.")
    return frozenset(_WEEKDAY_NAMES[name] for name in names)


def _parse_time_range(token: str) -> tuple[time, time]:
    start_text, _dash, end_text = token.partition("-")
    try:
        start_hour, start_minute = (int(part) for part in start_text.strip().split(":"))
        end_hour, end_minute = (int(part) for part in end_text.strip().split(":"))
        return time(start_hour, start_minute), time(end_hour, end_minute)
    except ValueError as exc:
        raise InvalidScheduleError(
            f"Invalid time range {token!r}; expected 'HH:MM-HH:MM'."
        ) from exc


def parse_calendar_rule(rule: str) -> CalendarRule:
    """Parse a calendar rule string (``"MON-FRI 09:00-17:00"``) into a :class:`CalendarRule`.

    Raises:
        InvalidScheduleError: If *rule* isn't in the expected
            ``"<weekdays> <HH:MM>-<HH:MM>"`` format.
    """
    parts = rule.strip().split()
    if len(parts) != _CALENDAR_RULE_TOKEN_COUNT:
        raise InvalidScheduleError(
            f"Invalid calendar rule {rule!r}; expected '<weekdays> <HH:MM>-<HH:MM>'."
        )
    weekday_token, time_token = parts
    weekdays = _parse_weekdays(weekday_token)
    start_time, end_time = _parse_time_range(time_token)
    return CalendarRule(weekdays=weekdays, start_time=start_time, end_time=end_time)


__all__ = ["CalendarRule", "parse_calendar_rule"]
